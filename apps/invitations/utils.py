import string
import secrets

def generate_invitation_code(length=8):
    """
    O'qish oson bo'lgan, xavfsiz random kod.
    Masalan: X7K9M2P4
    """
    alphabet = string.ascii_uppercase + string.digits
    # Adashtirib yuboradigan belgilarni olib tashlaymiz (0, O, I, 1)
    safe_alphabet = alphabet.translate(str.maketrans('', '', '0OI1'))
    return ''.join(secrets.choice(safe_alphabet) for _ in range(length))