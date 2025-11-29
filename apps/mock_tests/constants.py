"""
JLPT Constants - Standard JLPT structure and timing
"""

# JLPT Test Duration (in minutes) for each level
JLPT_DURATION = {
    'N5': {
        'total': 105,
        'moji_goi': 25,      # Vocabulary
        'bunpou_dokkai': 50,  # Grammar + Reading
        'choukai': 30,        # Listening
    },
    'N4': {
        'total': 125,
        'moji_goi': 30,
        'bunpou_dokkai': 60,
        'choukai': 35,
    },
    'N3': {
        'total': 140,
        'moji_goi': 30,
        'bunpou_dokkai': 70,
        'choukai': 40,
    },
    'N2': {
        'total': 155,
        'moji_goi_bunpou_dokkai': 105,  # Combined section
        'choukai': 50,
    },
    'N1': {
        'total': 170,
        'moji_goi_bunpou_dokkai': 110,
        'choukai': 60,
    },
}

# Standard JLPT Scoring
JLPT_SCORING = {
    'total_max': 180,           # Total maximum score
    'section_max': 60,          # Each section out of 60
    'passing_score': {
        'N5': 80,              # Minimum to pass
        'N4': 90,
        'N3': 95,
        'N2': 90,
        'N1': 100,
    },
    'section_minimum': 19,     # Minimum required in each section
}

# JLPT Mondai Types and their typical question counts
JLPT_MONDAI_STRUCTURE = {
    'N5': {
        'moji_goi': {
            'mondai_1': {'type': 'kanji_reading', 'questions': 12},
            'mondai_2': {'type': 'contextual_usage', 'questions': 8},
            'mondai_3': {'type': 'contextual_definition', 'questions': 10},
        },
        'bunpou': {
            'mondai_1': {'type': 'grammar_form', 'questions': 16},
            'mondai_2': {'type': 'sentence_composition', 'questions': 5},
            'mondai_3': {'type': 'text_grammar', 'questions': 5},
        },
        'dokkai': {
            'mondai_1': {'type': 'short_passage', 'questions': 2},
            'mondai_2': {'type': 'medium_passage', 'questions': 2},
            'mondai_3': {'type': 'information_retrieval', 'questions': 1},
        },
        'choukai': {
            'mondai_1': {'type': 'task_comprehension', 'questions': 6},
            'mondai_2': {'type': 'point_comprehension', 'questions': 6},
            'mondai_3': {'type': 'verbal_expression', 'questions': 5},
            'mondai_4': {'type': 'quick_response', 'questions': 6},
        },
    },
    'N4': {
        'moji_goi': {
            'mondai_1': {'type': 'kanji_reading', 'questions': 15},
            'mondai_2': {'type': 'orthography', 'questions': 5},
            'mondai_3': {'type': 'contextual_usage', 'questions': 10},
            'mondai_4': {'type': 'paraphrase', 'questions': 5},
        },
        'bunpou': {
            'mondai_1': {'type': 'grammar_form', 'questions': 15},
            'mondai_2': {'type': 'sentence_composition', 'questions': 5},
            'mondai_3': {'type': 'text_grammar', 'questions': 5},
        },
        'dokkai': {
            'mondai_1': {'type': 'short_passage', 'questions': 3},
            'mondai_2': {'type': 'medium_passage', 'questions': 3},
            'mondai_3': {'type': 'long_passage', 'questions': 2},
            'mondai_4': {'type': 'information_retrieval', 'questions': 1},
        },
        'choukai': {
            'mondai_1': {'type': 'task_comprehension', 'questions': 6},
            'mondai_2': {'type': 'point_comprehension', 'questions': 6},
            'mondai_3': {'type': 'verbal_expression', 'questions': 5},
            'mondai_4': {'type': 'quick_response', 'questions': 8},
        },
    },
    # N3, N2, N1 structures can be added similarly
}

# Mondai Type Descriptions
MONDAI_TYPE_DESCRIPTIONS = {
    'MOJI_GOI': 'Vocabulary (文字・語彙)',
    'BUNPOU': 'Grammar (文法)',
    'DOKKAI': 'Reading Comprehension (読解)',
    'CHOUKAI': 'Listening Comprehension (聴解)',
}

# Question Type Examples
QUESTION_TYPE_EXAMPLES = {
    'kanji_reading': 'Choose the correct reading of the underlined kanji',
    'orthography': 'Choose the correct kanji for the underlined hiragana',
    'contextual_usage': 'Choose the word that best fits the context',
    'contextual_definition': 'Choose the word closest in meaning',
    'paraphrase': 'Choose the sentence with similar meaning',
    'grammar_form': 'Choose the correct grammar form',
    'sentence_composition': 'Arrange words to form a correct sentence',
    'text_grammar': 'Fill in the blank with appropriate grammar',
    'short_passage': 'Answer questions about a short passage (200-300 chars)',
    'medium_passage': 'Answer questions about a medium passage (400-500 chars)',
    'long_passage': 'Answer questions about a long passage (600+ chars)',
    'information_retrieval': 'Find specific information from document',
    'task_comprehension': 'Listen and understand what task to do',
    'point_comprehension': 'Listen and understand key points',
    'verbal_expression': 'Listen and choose appropriate verbal response',
    'quick_response': 'Listen to short question and respond quickly',
}

# JLPT Level Descriptions
JLPT_LEVEL_INFO = {
    'N5': {
        'name': 'N5 - Beginner',
        'description': 'Basic level. Can understand basic Japanese.',
        'kanji_count': 100,
        'vocabulary_count': 800,
        'study_hours': 150,
    },
    'N4': {
        'name': 'N4 - Elementary',
        'description': 'Elementary level. Can understand basic Japanese.',
        'kanji_count': 300,
        'vocabulary_count': 1500,
        'study_hours': 300,
    },
    'N3': {
        'name': 'N3 - Intermediate',
        'description': 'Intermediate level. Can understand Japanese used in everyday situations.',
        'kanji_count': 650,
        'vocabulary_count': 3000,
        'study_hours': 450,
    },
    'N2': {
        'name': 'N2 - Upper Intermediate',
        'description': 'Upper intermediate level. Can understand Japanese in various situations.',
        'kanji_count': 1000,
        'vocabulary_count': 6000,
        'study_hours': 600,
    },
    'N1': {
        'name': 'N1 - Advanced',
        'description': 'Advanced level. Can understand Japanese in a broad range of situations.',
        'kanji_count': 2000,
        'vocabulary_count': 10000,
        'study_hours': 900,
    },
}