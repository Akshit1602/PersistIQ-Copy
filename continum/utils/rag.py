import os
from langchain_community.document_loaders import TextLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import FAISS
from langchain_openai import OpenAIEmbeddings
from langchain_core.embeddings import Embeddings

class SimpleEmbeddings(Embeddings):
    """
    Fallback embeddings using a simple hashing/projection if OpenAI is not available.
    In a real scenario, we'd use a local HuggingFace model.
    """
    def __init__(self):
        try:
            from sentence_transformers import SentenceTransformer
            self.model = SentenceTransformer('all-MiniLM-L6-v2')
            self.has_model = True
        except:
            self.has_model = False

    def embed_documents(self, texts):
        if self.has_model:
            return self.model.encode(texts).tolist()
        return [[0.0] * 384 for _ in texts]

    def embed_query(self, text):
        if self.has_model:
            return self.model.encode([text])[0].tolist()
        return [0.0] * 384

def get_embeddings():
    if os.getenv("OPENAI_API_KEY"):
        return OpenAIEmbeddings()
    return SimpleEmbeddings()

class READMEIndexer:
    def __init__(self, paths):
        self.paths = paths
        self.vectorstore = None

    def index(self):
        documents = []
        for path in self.paths:
            if os.path.exists(path):
                loader = TextLoader(path)
                documents.extend(loader.load())

        text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=100)
        docs = text_splitter.split_documents(documents)

        embeddings = get_embeddings()
        self.vectorstore = FAISS.from_documents(docs, embeddings)

    def search(self, query, k=3):
        if not self.vectorstore:
            self.index()
        return self.vectorstore.similarity_search(query, k=k)

_indexer = None

def get_readme_context(query):
    global _indexer
    if _indexer is None:
        _indexer = READMEIndexer(["README.md", "AskData/README.md"])
        try:
            _indexer.index()
        except Exception as e:
            print(f"Indexing failed: {e}")
            return ""

    docs = _indexer.search(query)
    return "\n\n".join([d.page_content for d in docs])
