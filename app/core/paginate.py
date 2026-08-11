

def paginate(query, page, page_size):
    return query.offset((page - 1) * page_size).limit(page_size).all()