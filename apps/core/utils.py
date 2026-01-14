import uuid

def generate_code(length=12):
    return str(uuid.uuid4()).replace("-", "")[:length]
