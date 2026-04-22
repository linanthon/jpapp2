from abc import ABC, abstractmethod
from enum import Enum

class BaseTextExtractor(ABC):
    @abstractmethod
    def stream_text(self, filename, chunk_size):
        """Yields chunks of text from file, chunk_size only applied to pure text files.
        encoded files like docx and pdf will read per paragraph / page"""
        pass

class TxtExtrator(BaseTextExtractor):
    def stream_text(self, filename, chunk_size):
        with open(filename, "r", encoding="utf-8") as f:
            while True:
                chunk = f.read(chunk_size)
                if not chunk:
                    break
                yield chunk

class DocxExtractor(BaseTextExtractor):
    def stream_text(self, filename, chunk_size=0):
        from docx import Document
        doc = Document(filename)
        for para in doc.paragraphs:
            if para.text:
                yield para.text + "\n"
    
class PdfExtractor(BaseTextExtractor):
    def stream_text(self, filename, chunk_size=0):
        from PyPDF2 import PdfReader
        reader = PdfReader(filename)
        for page in reader.pages:
            text = page.extract_text()
            if text:
                yield text
