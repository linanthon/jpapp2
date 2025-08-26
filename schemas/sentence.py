class Sentence:
    def __init__(self, sen_id=0, sentence="", star=False, occurence=0, quized=0):
        """
        - sentence (str): the sentence
        - star (bool): star the sentence
        - occurence (int): the times this word has appeared
        - quized (int): the times this word has been quized
        """
        self.sen_id = sen_id
        self.sen = sentence
        self.star = star
        self.occurrence = occurence
        self.quized = quized