# apps/attempts/services.py

from typing import Dict, Any, Tuple, Optional
import json
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.db import transaction, IntegrityError
from django.core.serializers.json import DjangoJSONEncoder
from decimal import Decimal
from .models import Submission
from apps.assignments.models import ExamAssignment, HomeworkAssignment
from apps.mock_tests.models import MockTest, TestSection, QuestionGroup, Question, Quiz, QuizQuestion


class StartExamService:
    """
    Service for starting an exam attempt.
    
    Handles:
    - Validation that ExamAssignment is OPEN
    - Validation that user hasn't already completed the exam
    - Creation of Submission record with status=STARTED
    """
    
    @staticmethod
    def start_exam(user, exam_assignment_id: str) -> Tuple[Submission, Dict[str, Any]]:
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
        
        # Create submission with DB-level uniqueness to avoid race conditions
        try:
            with transaction.atomic():
                submission = Submission.objects.create(
                    user_id=user.id,
                    exam_assignment=exam_assignment,
                    status=Submission.Status.STARTED,
                    started_at=timezone.now()
                )
        except IntegrityError:
            submission = Submission.objects.filter(
                user_id=user.id,
                exam_assignment=exam_assignment,
            ).first()
            if not submission:
                raise ValidationError("Unable to start exam at this time. Please retry.")
            if submission.status in (Submission.Status.SUBMITTED, Submission.Status.GRADED):
                raise ValidationError(
                    "You have already completed this exam. Each exam can only be attempted once."
                )
            if not submission.started_at:
                submission.started_at = timezone.now()
                submission.save(update_fields=['started_at'])
        
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
    def grade_submission(submission: Submission, student_answers: Dict[str, int]) -> Dict[str, Any]:
        """
        Grade a submission and SAVE in one atomic transaction.
        Immutability: Only STARTED submissions can be graded; once GRADED they cannot be modified.
        CRITICAL: Creates snapshot (including correct answers) before grading for historical integrity.
        
        Args:
            submission: Submission instance
            student_answers: Dict with format {question_uuid: selected_option_index}
            
        Returns:
            Dict: Grading results
            
        Raises:
            ValidationError: If submission is not STARTED or missing resource
        """
        snapshot_data = GradingService.create_snapshot(submission)
        with transaction.atomic():
            if submission.status != Submission.Status.STARTED:
                raise ValidationError(
                    f"Cannot grade submission with status: {submission.status}. Only STARTED submissions can be submitted."
                )
            if submission.mock_test:
                results = GradingService._grade_mock_test(submission.mock_test, student_answers, save=True)
            elif submission.quiz:
                results = GradingService._grade_quiz(submission.quiz, student_answers, save=True)
            elif submission.exam_assignment and submission.exam_assignment.mock_test:
                results = GradingService._grade_mock_test(
                    submission.exam_assignment.mock_test,
                    student_answers,
                    save=True,
                )
            else:
                raise ValidationError("Submission has no associated resource (MockTest or Quiz).")
            submission.answers = student_answers
            submission.completed_at = timezone.now()
            submission.status = Submission.Status.GRADED
            submission.score = Decimal(str(results["total_score"]))
            submission.results = results
            submission.snapshot = snapshot_data
            submission.save(update_fields=[
                "answers", "completed_at", "status", "score", "results", "snapshot",
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
        
        # Initialize section tracking with ALL questions to ensure correct max_score
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
            
            # Add question's max score to section max_score (whether answered or not)
            section_scores[section_id]['max_score'] += Decimal(str(question.score))
        
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
            
            # Store question result (no correct_index / is_correct leak; student sees only correct bool + score)
            section_question_results[section_id][question_id_str] = {
                'correct': is_correct,
                'score': float(question_score),
                'selected_index': selected_index,
            }
        
        total_score = sum((s["score"] for s in section_scores.values()), Decimal("0.00"))
        results = {
            "total_score": float(total_score),
            "sections": {},
            "jlpt_result": GradingService._calculate_jlpt_result(
                mock_test.level,
                total_score,
                section_scores,
            ),
            "resource_type": "mock_test",
        }
        
        for section_id, section_data in section_scores.items():
            section = section_data["section"]
            results["sections"][section_id] = {
                "section_id": section_id,
                "section_name": section.name,
                "section_type": section.section_type,
                "score": float(section_data["score"]),
                "max_score": float(section_data["max_score"]),
                "questions": section_question_results.get(section_id, {}),
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
            
            # Store question result (no correct_index leak)
            question_results[question_id_str] = {
                'correct': is_correct,
                'score': float(question_score),
                'points': question.points,
                'selected_index': selected_index,
            }
        
        percentage = (total_score / max_score * Decimal("100")).quantize(Decimal("0.01")) if max_score > 0 else Decimal("0.00")
        results = {
            "total_score": float(total_score),
            "max_score": float(max_score),
            "correct_count": correct_count,
            "total_count": total_count,
            "percentage": float(percentage),
            "questions": question_results,
            "resource_type": "quiz",
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
        Optimized with prefetch_related to avoid N+1 queries.
        """
        from apps.attempts.serializers import ExamPaperSerializer
        from django.db.models import Prefetch
        
        # Prefetch the entire hierarchy to avoid N+1
        mock_test = MockTest.objects.prefetch_related(
            Prefetch(
                'sections',
                queryset=TestSection.objects.select_related('mock_test').prefetch_related(
                    Prefetch(
                        'question_groups',
                        queryset=QuestionGroup.objects.select_related('section').prefetch_related(
                            Prefetch(
                                'questions',
                                queryset=Question.objects.select_related('group').order_by('order')
                            )
                        ).order_by('order')
                    )
                ).order_by('order')
            )
        ).get(id=mock_test.id)
        
        serializer = ExamPaperSerializer(mock_test)
        return serializer.data
    
    @staticmethod
    def _fetch_quiz_structure(quiz):
        """
        Fetch complete quiz structure for homework paper.
        Optimized with prefetch_related to avoid N+1 queries.
        """
        from apps.attempts.serializers import QuizPaperSerializer
        from django.db.models import Prefetch
        
        # Prefetch questions to avoid N+1
        quiz = Quiz.objects.prefetch_related(
            Prefetch(
                'questions',
                queryset=QuizQuestion.objects.select_related('quiz').order_by('order')
            )
        ).get(id=quiz.id)
        
        serializer = QuizPaperSerializer(quiz)
        return serializer.data
    
    @staticmethod
    def create_snapshot(submission):
        """
        Create a complete snapshot of the MockTest/Quiz at the exact moment of grading.
        
        Saves the full structure (sections, groups, questions, options) including
        correct_option_index and is_correct flags. If a teacher later deletes a question
        or changes the correct answer, the student's historical result remains unchanged
        because it was graded against this snapshot.
        
        Args:
            submission: Submission instance (must have mock_test, quiz, or exam_assignment.mock_test)
            
        Returns:
            dict: Complete snapshot with resource_type and snapshot_created_at
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
            snapshot_data = json.loads(json.dumps(serializer.data, cls=DjangoJSONEncoder))
            snapshot_data['resource_type'] = 'mock_test'
            snapshot_data['snapshot_created_at'] = timezone.now().isoformat()
        elif submission.quiz:
            # Quiz snapshot
            serializer = FullQuizSnapshotSerializer(submission.quiz)
            snapshot_data = json.loads(json.dumps(serializer.data, cls=DjangoJSONEncoder))
            snapshot_data['resource_type'] = 'quiz'
            snapshot_data['snapshot_created_at'] = timezone.now().isoformat()
        elif submission.exam_assignment and submission.exam_assignment.mock_test:
            # Legacy exam submission
            serializer = FullMockTestSnapshotSerializer(submission.exam_assignment.mock_test)
            snapshot_data = json.loads(json.dumps(serializer.data, cls=DjangoJSONEncoder))
            snapshot_data['resource_type'] = 'mock_test'
            snapshot_data['snapshot_created_at'] = timezone.now().isoformat()
        else:
            raise ValidationError("Cannot create snapshot: Submission has no associated resource.")
        
        return snapshot_data
    
    @staticmethod
    def _calculate_jlpt_result(level, total_score, section_scores):
        """
        JLPT pass/fail per official standards. FAIL if total below pass mark OR any
        section below minimum. All calculations use Decimal to avoid float errors.
        
        N1–N3: Three sections — Language Knowledge, Reading, Listening (each min 19).
        N4–N5: Two sections — Language Knowledge + Reading combined (120 pts, min 38),
               Listening (60 pts, min 19).
        """
        if level not in GradingService.JLPT_PASS_REQUIREMENTS:
            total_float = float(total_score) if isinstance(total_score, Decimal) else float(total_score)
            return {
                "level": level,
                "total_score": total_float,
                "pass_mark": None,
                "passed": None,
                "section_results": {},
                "error": f"Unknown JLPT level: {level}",
            }
        requirements = GradingService.JLPT_PASS_REQUIREMENTS[level]
        total_pass_mark = requirements["total_pass"]
        total_score_d = total_score if isinstance(total_score, Decimal) else Decimal(str(total_score))
        total_pass_mark_d = Decimal(str(total_pass_mark))

        section_results = {}
        all_sections_passed = True

        if level in ("N1", "N2", "N3"):
            lang_score = Decimal("0.00")
            reading_score = Decimal("0.00")
            listening_score = Decimal("0.00")
            for _sid, section_data in section_scores.items():
                section = section_data["section"]
                score = section_data["score"]
                if not isinstance(score, Decimal):
                    score = Decimal(str(score))
                if section.section_type == TestSection.SectionType.VOCAB:
                    lang_score += score
                elif section.section_type == TestSection.SectionType.GRAMMAR_READING:
                    half = score * Decimal("0.5")
                    lang_score += half
                    reading_score += half
                elif section.section_type == TestSection.SectionType.FULL_WRITTEN:
                    lang_score += score * Decimal("0.67")
                    reading_score += score * Decimal("0.33")
                elif section.section_type == TestSection.SectionType.LISTENING:
                    listening_score += score
            lang_min = Decimal(str(requirements["sections"]["language_knowledge"]))
            reading_min = Decimal(str(requirements["sections"]["reading"]))
            listening_min = Decimal(str(requirements["sections"]["listening"]))
            section_results = {
                "language_knowledge": {
                    "score": float(lang_score),
                    "min_required": int(lang_min),
                    "passed": lang_score >= lang_min,
                },
                "reading": {
                    "score": float(reading_score),
                    "min_required": int(reading_min),
                    "passed": reading_score >= reading_min,
                },
                "listening": {
                    "score": float(listening_score),
                    "min_required": int(listening_min),
                    "passed": listening_score >= listening_min,
                },
            }
            all_sections_passed = all(sr["passed"] for sr in section_results.values())

        elif level in ("N4", "N5"):
            lang_reading_score = Decimal("0.00")
            listening_score = Decimal("0.00")
            for _sid, section_data in section_scores.items():
                section = section_data["section"]
                score = section_data["score"]
                if not isinstance(score, Decimal):
                    score = Decimal(str(score))
                if section.section_type == TestSection.SectionType.LISTENING:
                    listening_score += score
                elif section.section_type in (
                    TestSection.SectionType.VOCAB,
                    TestSection.SectionType.GRAMMAR_READING,
                ):
                    lang_reading_score += score
            lang_read_min = Decimal(str(requirements["sections"]["language_reading_combined"]))
            listening_min = Decimal(str(requirements["sections"]["listening"]))
            section_results = {
                "language_reading_combined": {
                    "score": float(lang_reading_score),
                    "min_required": int(lang_read_min),
                    "passed": lang_reading_score >= lang_read_min,
                },
                "listening": {
                    "score": float(listening_score),
                    "min_required": int(listening_min),
                    "passed": listening_score >= listening_min,
                },
            }
            all_sections_passed = all(sr["passed"] for sr in section_results.values())

        total_passed = total_score_d >= total_pass_mark_d
        passed = total_passed and all_sections_passed
        return {
            "level": level,
            "total_score": float(total_score_d),
            "pass_mark": int(total_pass_mark),
            "passed": passed,
            "section_results": section_results,
            "total_passed": total_passed,
            "all_sections_passed": all_sections_passed,
        }
