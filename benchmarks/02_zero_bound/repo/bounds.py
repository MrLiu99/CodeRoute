def clamp(value, lower=None, upper=None):
    if lower and value < lower:
        value = lower
    if upper and value > upper:
        value = upper
    return value
