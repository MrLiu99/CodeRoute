def weighted_mean(values, weights):
    if len(values) != len(weights) or not values:
        raise ValueError('nonempty equal lengths required')
    return sum(v * w for v, w in zip(values, weights)) / len(values)
