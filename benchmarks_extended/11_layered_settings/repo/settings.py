from merge import merge

def load_settings(defaults, overrides, environ):
    result = merge(defaults, overrides)
    if 'APP_ENABLED' in environ:
        result['enabled'] = bool(environ['APP_ENABLED'])
    return result
