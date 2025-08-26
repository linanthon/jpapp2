class Book:
    def __init__(self, book_id=0, name="", content=""):
        """
        - namne (str): the document's name
        - content (bool): the document's content
        """
        self.book_id = book_id
        self.name = name
        self.content = content