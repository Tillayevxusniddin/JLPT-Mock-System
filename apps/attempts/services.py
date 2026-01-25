# apps/attempts/services.py

from django.utils import timezone
from django.core.exceptions import ValidationError
from django.db import transaction
from decimal import Decimal
from .models import Submission
from apps.assignments.models import ExamAssignment, HomeworkAssignment
from apps.mock_tests.models import MockTest, TestSection, Question, Quiz, QuizQuestion


class StartExamService:
    """
    Service for starting an exam attempt.
    
    Handles:
    - Validation that ExamAssignment is OPEN
    - Validation that user hasn't already completed the exam
    - Creation of Submission record with status=STARTED
    """
    
    @staticmethod
    @transaction.atomic
    def start_exam(user, exam_assignment_id):
        """
        Start an exam for a user.
        
        Args:
            user: User instance
            exam_assignment_id: UUID of ExamAssignment
            
        Returns:
            tuple: (submission, exam_paper_data)
            
        Raises:
            ValidationError: If validation fails
        """
        # Fetch exam assignment
        try:
            exam_assignment = ExamAssignment.objects.select_related('mock_test').get(
                id=exam_assignment_id
            )
        except ExamAssignment.DoesNotExist:
            raise ValidationError("Exam assignment not found.")
        
        # Validate exam assignment is OPEN
        if exam_assignment.status != ExamAssignment.RoomStatus.OPEN:
            raise ValidationError(
                f"Exam is not open. Current status: {exam_assignment.status}"
            )
        
        # Validate mock_test exists and is PUBLISHED
        if not exam_assignment.mock_test:
            raise ValidationError("Exam assignment has no mock test assigned.")
        
        if exam_assignment.mock_test.status != MockTest.Status.PUBLISHED:
            raise ValidationError("Mock test is not published.")
        
        # Check if user already has a completed submission
        existing_submission = Submission.objects.filter(
            user_id=user.id,
            exam_assignment=exam_assignment,
            status__in=[Submission.Status.SUBMITTED, Submission.Status.GRADED]
        ).first()
        
        if existing_submission:
            raise ValidationError(
                "You have already completed this exam. Each exam can only be attempted once."
            )
        
        # Check if user has a STARTED submission (resume exam)
        started_submission = Submission.objects.filter(
            user_id=user.id,
            exam_assignment=exam_assignment,
            status=Submission.Status.STARTED
        ).first()
        
        if started_submission:
            # Resume existing submission
            submission = started_submission
            if not submission.started_at:
                submission.started_at = timezone.now()
                submission.save(update_fields=['started_at'])
        else:
            # Create new submission
            submission = Submission.objects.create(
                user_id=user.id,
                exam_assignment=exam_assignment,
                status=Submission.Status.STARTED,
                started_at=timezone.now()
            )
        
        # Fetch exam paper data (MockTest with all nested structures)
        mock_test = exam_assignment.mock_test
        exam_paper_data = GradingService._fetch_mock_test_structure(mock_test)
        
        return submission, exam_paper_data


class StartHomeworkService:
    """
    Service for starting a homework item (MockTest or Quiz).
    
    Handles:
    - Validation that HomeworkAssignment deadline hasn't passed
    - Validation that item belongs to the homework
    - Creation/Resume of Submission record with status=STARTED
    """
    
    @staticmethod
    @transaction.atomic
    def start_homework_item(user, homework_assignment_id, item_type, item_id):
        """
        Start a homework item (MockTest or Quiz) for a user.
        
        Args:
            user: User instance
            homework_assignment_id: UUID of HomeworkAssignment
            item_type: 'mock_test' or 'quiz'
            item_id: UUID of MockTest or Quiz
            
        Returns:
            tuple: (submission, item_data)
            
        Raises:
            ValidationError: If validation fails
        """
        # Fetch homework assignment
        try:
            homework = HomeworkAssignment.objects.prefetch_related(
                'mock_tests', 'quizzes'
            ).get(id=homework_assignment_id)
        except HomeworkAssignment.DoesNotExist:
            raise ValidationError("Homework assignment not found.")
        
        # Validate deadline hasn't passed
        if homework.deadline <= timezone.now():
            raise ValidationError(
                f"Homework deadline has passed. Deadline was: {homework.deadline}"
            )
        
        # Validate item belongs to homework
        if item_type == 'mock_test':
            if not homework.mock_tests.filter(id=item_id).exists():
                raise ValidationError(
                    "This MockTest is not assigned to this homework."
                )
            resource = MockTest.objects.get(id=item_id)
            if resource.status != MockTest.Status.PUBLISHED:
                raise ValidationError("MockTest is not published.")
        elif item_type == 'quiz':
            if not homework.quizzes.filter(id=item_id).exists():
                raise ValidationError(
                    "This Quiz is not assigned to this homework."
                )
            resource = Quiz.objects.get(id=item_id)
            if not resource.is_active:
                raise ValidationError("Quiz is not active.")
        else:
            raise ValidationError(f"Invalid item_type: {item_type}. Must be 'mock_test' or 'quiz'.")
        
        # Check if user already has a GRADED submission (locked)
        existing_submission = Submission.objects.filter(
            user_id=user.id,
            homework_assignment=homework,
            status=Submission.Status.GRADED
        )
        if item_type == 'mock_test':
            existing_submission = existing_submission.filter(mock_test_id=item_id)
        else:
            existing_submission = existing_submission.filter(quiz_id=item_id)
        
        if existing_submission.exists():
            raise ValidationError(
                "You have already submitted this item. It cannot be retaken."
            )
        
        # Check if user has a STARTED submission (resume)
        started_submission = Submission.objects.filter(
            user_id=user.id,
            homework_assignment=homework,
            status=Submission.Status.STARTED
        )
        if item_type == 'mock_test':
            started_submission = started_submission.filter(mock_test_id=item_id)
        else:
            started_submission = started_submission.filter(quiz_id=item_id)
        
        started_submission = started_submission.first()
        
        if started_submission:
            # Resume existing submission
            submission = started_submission
            if not submission.started_at:
                submission.started_at = timezone.now()
                submission.save(update_fields=['started_at'])
        else:
            # Create new submission
            submission = Submission.objects.create(
                user_id=user.id,
                homework_assignment=homework,
                status=Submission.Status.STARTED,
                started_at=timezone.now(),
                **{item_type: resource}
            )
        
        # Fetch item data (without correct answers)
        if item_type == 'mock_test':
            item_data = GradingService._fetch_mock_test_structure(resource)
        else:
            item_data = GradingService._fetch_quiz_structure(resource)
        
        return submission, item_data


class GradingService:
    """
    Service for grading submissions (both MockTest and Quiz).
    
    Implements:
    - JLPT scoring logic for MockTests
    - Simple scoring logic for Quizzes
    - Practice mode (dry-run) for homework items
    """
    
    # JLPT Pass Requirements by Level
    JLPT_PASS_REQUIREMENTS = {
        'N1': {
            'total_pass': 100,
            'sections': {
                'language_knowledge': 19,
                'reading': 19,
                'listening': 19
            }
        },
        'N2': {
            'total_pass': 90,
            'sections': {
                'language_knowledge': 19,
                'reading': 19,
                'listening': 19
            }
        },
        'N3': {
            'total_pass': 95,
            'sections': {
                'language_knowledge': 19,
                'reading': 19,
                'listening': 19
            }
        },
        'N4': {
            'total_pass': 90,
            'sections': {
                'language_reading_combined': 38,  # Combined Language Knowledge + Reading
                'listening': 19
            }
        },
        'N5': {
            'total_pass': 80,
            'sections': {
                'language_reading_combined': 38,  # Combined Language Knowledge + Reading
                'listening': 19
            }
        }
    }
    
    @staticmethod
    def calculate_result_dry_run(submission, student_answers):
        """
        Calculate grading result WITHOUT saving (practice mode).
        
        This method is used for 'show-result' action in homework.
        It returns the grading result but does NOT:
        - Set completed_at
        - Change status to GRADED
        - Lock the submission
        
        Args:
            submission: Submission instance
            student_answers: dict with format {question_uuid: selected_option_index}
            
        Returns:
            dict: Grading results (same format as grade_submission)
        """
        # Determine resource type
        if submission.mock_test:
            return GradingService._grade_mock_test(submission.mock_test, student_answers, save=False)
        elif submission.quiz:
            return GradingService._grade_quiz(submission.quiz, student_answers, save=False)
        else:
            raise ValidationError("Submission has no associated resource (MockTest or Quiz).")
    
    @staticmethod
    @transaction.atomic
    def grade_submission(submission, student_answers):
        """
        Grade a submission based on student answers and SAVE the results.
        
        CRITICAL: Before grading, saves a complete snapshot of the test/quiz
        (including correct answers) to preserve historical integrity.
        
        Args:
            submission: Submission instance
            student_answers: dict with format {question_uuid: selected_option_index}
            
        Returns:
            dict: Grading results
        """
        # Validate submission status
        if submission.status not in [Submission.Status.STARTED, Submission.Status.SUBMITTED]:
            raise ValidationError(f"Cannot grade submission with status: {submission.status}")
        
        # CRITICAL: Save snapshot BEFORE grading to preserve test state
        snapshot_data = GradingService.create_snapshot(submission)
        
        # Determine resource type and grade accordingly
        if submission.mock_test:
            results = GradingService._grade_mock_test(submission.mock_test, student_answers, save=True)
        elif submission.quiz:
            results = GradingService._grade_quiz(submission.quiz, student_answers, save=True)
        elif submission.exam_assignment and submission.exam_assignment.mock_test:
            # Legacy exam submission
            results = GradingService._grade_mock_test(
                submission.exam_assignment.mock_test,
                student_answers,
                save=True
            )
        else:
            raise ValidationError("Submission has no associated resource (MockTest or Quiz).")
        
        # Update submission with snapshot, answers, and results
        submission.answers = student_answers
        submission.completed_at = timezone.now()
        submission.status = Submission.Status.GRADED
        submission.score = Decimal(str(results['total_score']))
        submission.results = results
        submission.snapshot = snapshot_data  # Save snapshot for historical integrity
        submission.save(update_fields=[
            'answers', 'completed_at', 'status', 'score', 'results', 'snapshot'
        ])
        
        return results
    
    @staticmethod
    def _grade_mock_test(mock_test, student_answers, save=False):
        """
        Grade a MockTest submission using JLPT logic.
        
        Args:
            mock_test: MockTest instance
            student_answers: dict with format {question_uuid: selected_option_index}
            save: Whether to save results (unused, kept for API consistency)
            
        Returns:
            dict: Grading results
        """
        # Fetch all questions with optimized query
        questions = GradingService._fetch_questions(mock_test)
        
        # Create question lookup dict
        question_dict = {str(q.id): q for q in questions}
        
        # Calculate scores
        total_score = Decimal('0.00')
        section_scores = {}
        section_question_results = {}
        
        # Initialize section tracking
        for question in questions:
            section_id = str(question.group.section.id)
            if section_id not in section_scores:
                section_scores[section_id] = {
                    'section': question.group.section,
                    'score': Decimal('0.00'),
                    'max_score': Decimal('0.00'),
                    'questions': {}
                }
                section_question_results[section_id] = {}
        
        # Grade each answer
        for question_id_str, selected_index in student_answers.items():
            if question_id_str not in question_dict:
                # Question not found (might have been deleted)
                continue
            
            question = question_dict[question_id_str]
            section_id = str(question.group.section.id)
            
            # Check if answer is correct
            is_correct = (
                question.correct_option_index is not None and
                selected_index == question.correct_option_index
            )
            
            # Calculate score for this question
            question_score = Decimal(str(question.score)) if is_correct else Decimal('0.00')
            
            # Add to section score
            section_scores[section_id]['score'] += question_score
            section_scores[section_id]['max_score'] += Decimal(str(question.score))
            
            # Store question result
            section_question_results[section_id][question_id_str] = {
                'correct': is_correct,
                'score': float(question_score),
                'selected_index': selected_index,
                'correct_index': question.correct_option_index
            }
        
        # Calculate total score
        total_score = sum(s['score'] for s in section_scores.values())
        
        # Build results structure
        results = {
            'total_score': float(total_score),
            'sections': {},
            'jlpt_result': GradingService._calculate_jlpt_result(
                mock_test.level,
                total_score,
                section_scores
            ),
            'resource_type': 'mock_test'
        }
        
        # Add section details
        for section_id, section_data in section_scores.items():
            section = section_data['section']
            results['sections'][section_id] = {
                'section_id': section_id,
                'section_name': section.name,
                'section_type': section.section_type,
                'score': float(section_data['score']),
                'max_score': float(section_data['max_score']),
                'questions': section_question_results.get(section_id, {})
            }
        
        return results
    
    @staticmethod
    def _grade_quiz(quiz, student_answers, save=False):
        """
        Grade a Quiz submission using simple scoring logic.
        
        Args:
            quiz: Quiz instance
            student_answers: dict with format {question_uuid: selected_option_index}
            save: Whether to save results (unused, kept for API consistency)
            
        Returns:
            dict: Grading results
        """
        # Fetch all quiz questions
        questions = QuizQuestion.objects.filter(
            quiz=quiz
        ).order_by('order')
        
        # Create question lookup dict
        question_dict = {str(q.id): q for q in questions}
        
        # Calculate scores
        total_score = Decimal('0.00')
        max_score = Decimal('0.00')
        question_results = {}
        correct_count = 0
        total_count = len(questions)
        
        # Grade each answer
        for question_id_str, selected_index in student_answers.items():
            if question_id_str not in question_dict:
                continue
            
            question = question_dict[question_id_str]
            max_score += Decimal(str(question.points))
            
            # Check if answer is correct
            is_correct = (
                question.correct_option_index is not None and
                selected_index == question.correct_option_index
            )
            
            # Calculate score for this question
            question_score = Decimal(str(question.points)) if is_correct else Decimal('0.00')
            total_score += question_score
            
            if is_correct:
                correct_count += 1
            
            # Store question result
            question_results[question_id_str] = {
                'correct': is_correct,
                'score': float(question_score),
                'points': question.points,
                'selected_index': selected_index,
                'correct_index': question.correct_option_index
            }
        
        # Build results structure
        results = {
            'total_score': float(total_score),
            'max_score': float(max_score),
            'correct_count': correct_count,
            'total_count': total_count,
            'percentage': float(total_score / max_score * 100) if max_score > 0 else 0.0,
            'questions': question_results,
            'resource_type': 'quiz'
        }
        
        return results
    
    @staticmethod
    def _fetch_questions(mock_test):
        """
        Fetch all questions for a mock test with optimized query.
        """
        return Question.objects.filter(
            group__section__mock_test=mock_test
        ).select_related(
            'group', 'group__section'
        ).order_by(
            'group__section__order',
            'group__order',
            'order'
        )
    
    @staticmethod
    def _fetch_mock_test_structure(mock_test):
        """
        Fetch complete mock test structure for exam paper.
        Used by StartExamService to return exam paper data.
        """
        from apps.attempts.serializers import ExamPaperSerializer
        
        serializer = ExamPaperSerializer(mock_test)
        return serializer.data
    
    @staticmethod
    def _fetch_quiz_structure(quiz):
        """
        Fetch complete quiz structure for homework paper.
        """
        from apps.attempts.serializers import QuizPaperSerializer
        
        serializer = QuizPaperSerializer(quiz)
        return serializer.data
    
    @staticmethod
    def create_snapshot(submission):
        """
        Create a complete snapshot of the MockTest/Quiz at the time of grading.
        
        This snapshot includes ALL data including correct answers, preserving
        the exact state of the test for historical integrity.
        
        Args:
            submission: Submission instance
            
        Returns:
            dict: Complete snapshot data with resource_type indicator
        """
        from apps.attempts.serializers import (
            FullMockTestSnapshotSerializer,
            FullQuizSnapshotSerializer
        )
        
        snapshot_data = {}
        
        # Determine resource type and create appropriate snapshot
        if submission.mock_test:
            # MockTest snapshot
            serializer = FullMockTestSnapshotSerializer(submission.mock_test)
            snapshot_data = serializer.data
            snapshot_data['resource_type'] = 'mock_test'
            snapshot_data['snapshot_created_at'] = timezone.now().isoformat()
        elif submission.quiz:
            # Quiz snapshot
            serializer = FullQuizSnapshotSerializer(submission.quiz)
            snapshot_data = serializer.data
            snapshot_data['resource_type'] = 'quiz'
            snapshot_data['snapshot_created_at'] = timezone.now().isoformat()
        elif submission.exam_assignment and submission.exam_assignment.mock_test:
            # Legacy exam submission
            serializer = FullMockTestSnapshotSerializer(submission.exam_assignment.mock_test)
            snapshot_data = serializer.data
            snapshot_data['resource_type'] = 'mock_test'
            snapshot_data['snapshot_created_at'] = timezone.now().isoformat()
        else:
            raise ValidationError("Cannot create snapshot: Submission has no associated resource.")
        
        return snapshot_data
    
    @staticmethod
    def _calculate_jlpt_result(level, total_score, section_scores):
        """
        Calculate JLPT pass/fail result based on level and scores.
        
        Args:
            level: MockTest level (N1, N2, N3, N4, N5)
            total_score: Total score achieved
            section_scores: Dict of section_id -> section data
            
        Returns:
            dict: JLPT result with pass/fail status
        """
        if level not in GradingService.JLPT_PASS_REQUIREMENTS:
            return {
                'level': level,
                'total_score': float(total_score),
                'pass_mark': None,
                'passed': None,
                'section_results': {},
                'error': f'Unknown JLPT level: {level}'
            }
        
        requirements = GradingService.JLPT_PASS_REQUIREMENTS[level]
        total_pass_mark = requirements['total_pass']
        
        # Group sections by JLPT scoring categories
        section_results = {}
        all_sections_passed = True
        
        if level in ['N1', 'N2', 'N3']:
            # Three separate sections: Language Knowledge, Reading, Listening
            # Each section max 60, total 180
            language_knowledge_score = Decimal('0.00')
            reading_score = Decimal('0.00')
            listening_score = Decimal('0.00')
            
            for section_id, section_data in section_scores.items():
                section = section_data['section']
                score = section_data['score']
                
                if section.section_type == TestSection.SectionType.VOCAB:
                    # Vocabulary contributes to Language Knowledge
                    language_knowledge_score += score
                elif section.section_type == TestSection.SectionType.GRAMMAR_READING:
                    # Grammar/Reading section: Grammar part -> Language Knowledge, Reading part -> Reading
                    # For simplicity, split 50/50, but in real JLPT, this would be based on question distribution
                    # In practice, you might want to track this more precisely based on question types
                    language_knowledge_score += score * Decimal('0.5')
                    reading_score += score * Decimal('0.5')
                elif section.section_type == TestSection.SectionType.FULL_WRITTEN:
                    # N1/N2: Full Written section contains Vocab + Grammar + Reading
                    # Split: Vocab+Grammar -> Language Knowledge, Reading -> Reading
                    # Approximate split: 2/3 to Language Knowledge, 1/3 to Reading
                    language_knowledge_score += score * Decimal('0.67')
                    reading_score += score * Decimal('0.33')
                elif section.section_type == TestSection.SectionType.LISTENING:
                    listening_score += score
            
            # Check pass requirements
            lang_min = requirements['sections']['language_knowledge']
            reading_min = requirements['sections']['reading']
            listening_min = requirements['sections']['listening']
            
            section_results = {
                'language_knowledge': {
                    'score': float(language_knowledge_score),
                    'min_required': lang_min,
                    'passed': float(language_knowledge_score) >= lang_min
                },
                'reading': {
                    'score': float(reading_score),
                    'min_required': reading_min,
                    'passed': float(reading_score) >= reading_min
                },
                'listening': {
                    'score': float(listening_score),
                    'min_required': listening_min,
                    'passed': float(listening_score) >= listening_min
                }
            }
            
            all_sections_passed = all(
                sr['passed'] for sr in section_results.values()
            )
        
        elif level in ['N4', 'N5']:
            # Two sections: Language Knowledge + Reading (combined), Listening
            language_reading_score = Decimal('0.00')
            listening_score = Decimal('0.00')
            
            for section_id, section_data in section_scores.items():
                section = section_data['section']
                score = section_data['score']
                
                if section.section_type == TestSection.SectionType.LISTENING:
                    listening_score += score
                else:
                    # All other sections contribute to Language + Reading combined
                    language_reading_score += score
            
            # Check pass requirements
            lang_read_min = requirements['sections']['language_reading_combined']
            listening_min = requirements['sections']['listening']
            
            section_results = {
                'language_reading_combined': {
                    'score': float(language_reading_score),
                    'min_required': lang_read_min,
                    'passed': float(language_reading_score) >= lang_read_min
                },
                'listening': {
                    'score': float(listening_score),
                    'min_required': listening_min,
                    'passed': float(listening_score) >= listening_min
                }
            }
            
            all_sections_passed = all(
                sr['passed'] for sr in section_results.values()
            )
        
        # Final pass/fail determination
        total_passed = float(total_score) >= total_pass_mark
        passed = total_passed and all_sections_passed
        
        return {
            'level': level,
            'total_score': float(total_score),
            'pass_mark': total_pass_mark,
            'passed': passed,
            'section_results': section_results,
            'total_passed': total_passed,
            'all_sections_passed': all_sections_passed
        }
