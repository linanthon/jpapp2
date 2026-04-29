from abc import ABC, abstractmethod
import io

class BaseTextExtractor(ABC):
    @abstractmethod
    def stream_text(self, file_obj, chunk_size):
        """Yield chunks of text from a binary file-like object.
        chunk_size is only applied to plain text files.
        Encoded files like docx and pdf are read per paragraph/page.
        """
        pass

class TxtExtractor(BaseTextExtractor):
    def stream_text(self, file_obj, chunk_size=4096):
        if hasattr(file_obj, "seek"):
            file_obj.seek(0)

        while True:
            chunk = file_obj.read(chunk_size)
            if not chunk:
                break

            if isinstance(chunk, bytes):
                yield chunk.decode("utf-8", errors="ignore")
            else:
                yield str(chunk)

class DocxExtractor(BaseTextExtractor):
    def stream_text(self, file_obj, chunk_size=0):
        from docx import Document

        if hasattr(file_obj, "seek"):
            file_obj.seek(0)

        doc = Document(io.BytesIO(file_obj.read()))
        for para in doc.paragraphs:
            if para.text:
                yield para.text + "\n"
    
class PdfExtractor(BaseTextExtractor):
    def stream_text(self, file_obj, chunk_size=0):
        import fitz

        if hasattr(file_obj, "seek"):
            file_obj.seek(0)

        reader = fitz.open(stream=file_obj.read(), filetype="pdf")
        try:
            for page in reader:
                text = page.get_text()
                if text:
                    yield text
        finally:
            reader.close()
