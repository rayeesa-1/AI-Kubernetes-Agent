import shlex


def validate_recommendations(diagnosis):
    for command in diagnosis.kubectl_commands:
        if len(command) > 800 or any(char in command for char in (";", "|", "&", "`", "$", ">", "<", "\n", "\r")):
            raise ValueError("AI suggested shell syntax rather than a single kubectl command")
        parts = shlex.split(command)
        if len(parts) < 2 or parts[0] != "kubectl":
            raise ValueError("AI suggested an unsupported command")
    return diagnosis
