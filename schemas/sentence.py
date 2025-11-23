class Sentence:
    def __init__(self, sen_id=0, sentence="", star=False, occurrence=0, quized=0):
        """
        - sentence (str): the sentence
        - star (bool): star the sentence
        - occurrence (int): the times this word has appeared
        - quized (int): the times this word has been quized
        """
        self.sen_id = sen_id
        self.sen = sentence
        self.star = star
        self.occurrence = occurrence
        self.quized = quized