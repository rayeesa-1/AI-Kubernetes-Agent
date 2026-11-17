def resolve_pointer(document, pointer):
    if not isinstance(pointer, str) or not pointer.startswith("/"):
        return False
    value = document
    try:
        for part in pointer[1:].split("/"):
            key = part.replace("~1", "/").replace("~0", "~")
            if isinstance(value, list):
                if not key.isdigit():
                    return False
                value = value[int(key)]
            elif isinstance(value, dict):
                value = value[key]
            else:
                return False
        return value is not None
    except (KeyError, IndexError, TypeError, ValueError):
        return False


def assess_confidence(diagnosis, evidence, collection_status):
    references = diagnosis.evidence_references
    valid = [ref for ref in references if resolve_pointer(evidence, ref)]
    if len(valid) != len(references):
        raise ValueError("AI returned references outside the supplied evidence")
    # Transparent conservative caps; these are not calibrated probabilities.
    if not valid:
        diagnosis.confidence = min(diagnosis.confidence, 20)
        diagnosis.confidence_reasoning += " No verifiable evidence references were supplied; capped at 20."
    if collection_status != "success":
        diagnosis.confidence = min(diagnosis.confidence, 60)
        diagnosis.confidence_reasoning += " Collection was incomplete; capped at 60."
    if diagnosis.missing_evidence:
        diagnosis.confidence = min(diagnosis.confidence, 75)
    return diagnosis
