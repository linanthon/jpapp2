class Book:
    def __init__(self, book_id=0, name="", created_at="", star=False, content=""):
        """
        - name (str): the document's name
        - created_at (str): the book inserted timestamp
        - star (bool): starred or not
        - content (str): the document's content
        """
        self.book_id = book_id
        self.name = name
        self.created_at = created_at
        self.star = star
        self.content = content
