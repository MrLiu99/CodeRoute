def page_items(items, page, size):
    if page < 1 or size < 1:
        raise ValueError('positive page and size required')
    start = page * size
    return items[start:start + size]
