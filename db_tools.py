# db_tools.py

import subprocess
import sys
import logging
import os
import faiss
import numpy as np
from typing import List, Dict, Any
from langchain_community.document_loaders import PyPDFLoader, CSVLoader, TextLoader
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_core.documents import Document
import json
import shutil
import uuid  # For generating unique chunk IDs
import docx  # For .docx files
import tempfile

# Try to import Windows-specific modules, but don't fail if they're not available
try:
    import win32com.client
    import pythoncom
    WORD_SUPPORT = True
except ImportError:
    WORD_SUPPORT = False
    logging.warning("win32com not available. Legacy .doc file support will be disabled.")

# Setup logging
LOG_DIR = "logs"
if not os.path.exists(LOG_DIR):
    os.makedirs(LOG_DIR)

logging.basicConfig(
    filename=os.path.join(LOG_DIR, "app.log"),
    filemode='a',
    format='%(asctime)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

DATABASES_DIR = "databases"

class DatabaseManager:
    def __init__(self):
        # Switch to a more robust model
        self.embeddings = HuggingFaceEmbeddings(model_name="all-MiniLM-L12-v2")
        if not os.path.exists(DATABASES_DIR):
            os.makedirs(DATABASES_DIR)
        logging.info("Initialized DatabaseManager.")
    
    def preprocess_content(self, content: str) -> str:
        """
        Preprocess the content by removing irrelevant sections.
        
        Args:
            content (str): The raw text content.
        
        Returns:
            str: The cleaned text content.
        """
        # Example: Remove lines containing certain keywords
        keywords = ['page', 'copyright', 'confidential', 'scan the qr code', 'seats', 'policies', 'help']
        lines = content.split('\n')
        filtered_lines = [line for line in lines if not any(keyword in line.lower() for keyword in keywords)]
        return '\n'.join(filtered_lines)
    
    def _get_file_type(self, uploaded_file: Any) -> str:
        """
        Determine the file type based on the file extension.

        Args:
            uploaded_file (file object): File object opened in binary mode.

        Returns:
            str: The file type ('pdf', 'csv', 'txt', 'docx', 'doc', etc.).
        """
        _, ext = os.path.splitext(uploaded_file.name)
        file_type = ext.lower().lstrip('.')
        logging.debug(f"Determined file type '{file_type}' for file '{uploaded_file.name}'.")
        return file_type

    def _save_uploaded_file(self, db_name: str, uploaded_file: Any) -> str:
        """
        Save the uploaded file to the specified database directory.

        Args:
            db_name (str): Name of the database.
            uploaded_file (file object): File object opened in binary mode.

        Returns:
            str: Path to the saved file.
        """
        db_path = os.path.join(DATABASES_DIR, db_name)
        # Use os.path.basename to get only the file name, avoiding full path issues
        file_name = os.path.basename(uploaded_file.name)
        file_path = os.path.join(db_path, file_name)
        try:
            with open(file_path, "wb") as f:
                f.write(uploaded_file.read())  # Use read() instead of getbuffer()
            logging.info(f"Saved uploaded file '{uploaded_file.name}' to '{file_path}'.")
            return file_path
        except Exception as e:
            logging.error(f"Failed to save uploaded file '{uploaded_file.name}': {e}")
            raise e

    def _extract_text_from_docx(self, file_path: str) -> str:
        """
        Extract text from a .docx file.
        
        Args:
            file_path (str): Path to the .docx file.
            
        Returns:
            str: Extracted text content.
        """
        try:
            doc = docx.Document(file_path)
            text = []
            for paragraph in doc.paragraphs:
                if paragraph.text.strip():  # Skip empty paragraphs
                    text.append(paragraph.text)
            for table in doc.tables:
                for row in table.rows:
                    row_text = []
                    for cell in row.cells:
                        if cell.text.strip():  # Skip empty cells
                            row_text.append(cell.text)
                    if row_text:  # Skip empty rows
                        text.append(" | ".join(row_text))
            return "\n".join(text)
        except Exception as e:
            logging.error(f"Error extracting text from .docx file '{file_path}': {e}")
            raise

    def _extract_text_from_doc(self, file_path: str) -> str:
        """
        Extract text from a legacy .doc file using Word COM object.
        
        Args:
            file_path (str): Path to the .doc file.
            
        Returns:
            str: Extracted text content.
        """
        if not WORD_SUPPORT:
            raise ImportError("win32com is not available. Cannot process .doc files.")
            
        try:
            pythoncom.CoInitialize()  # Initialize COM
            word = win32com.client.Dispatch("Word.Application")
            word.Visible = False
            
            # Create a temporary file for the .docx version
            with tempfile.NamedTemporaryFile(suffix='.docx', delete=False) as temp_file:
                temp_path = temp_file.name
            
            try:
                # Open and save as .docx
                doc = word.Documents.Open(file_path)
                doc.SaveAs2(temp_path, FileFormat=16)  # 16 = .docx format
                doc.Close()
                
                # Extract text from the .docx version
                text = self._extract_text_from_docx(temp_path)
                
                return text
            finally:
                word.Quit()
                # Clean up the temporary file
                if os.path.exists(temp_path):
                    os.unlink(temp_path)
                pythoncom.CoUninitialize()
        except Exception as e:
            logging.error(f"Error extracting text from .doc file '{file_path}': {e}")
            raise

    def add_documents(self, db_name: str, uploaded_files: List[Any]) -> Dict[str, Any]:
        """
        Add documents to the specified database.

        Args:
            db_name (str): Name of the database.
            uploaded_files (List[Any]): List of file objects opened in binary mode.

        Returns:
            Dict[str, Any]: Result of the operation.
        """
        try:
            # Load current index and metadata
            index = self.load_faiss_index(db_name)
            if index is None:
                # FAISS index not found; attempt to create it
                logging.warning(f"FAISS index not found for database '{db_name}'. Creating a new index.")
                success = self.create_database(db_name)
                if not success:
                    error_msg = "Failed to create FAISS index."
                    logging.error(error_msg)
                    return {"success": False, "error": error_msg}
                index = self.load_faiss_index(db_name)
                if index is None:
                    error_msg = "FAISS index could not be initialized."
                    logging.error(error_msg)
                    return {"success": False, "error": error_msg}

            metadata = self.load_metadata(db_name)

            # Track already processed files to prevent duplicates
            existing_files = set(meta['source'] for meta in metadata)

            # Process each uploaded file
            for uploaded_file in uploaded_files:
                if uploaded_file.name in existing_files:
                    logging.warning(f"File '{uploaded_file.name}' already exists in the database. Skipping duplicate.")
                    continue  # Skip duplicate files

                file_path = self._save_uploaded_file(db_name, uploaded_file)
                file_type = self._get_file_type(uploaded_file)
                
                # Get the document content based on file type
                if file_type == 'pdf':
                    loader = PyPDFLoader(file_path)
                    documents = loader.load()
                elif file_type == 'csv':
                    loader = CSVLoader(file_path)
                    documents = loader.load()
                elif file_type == 'txt':
                    loader = TextLoader(file_path)
                    documents = loader.load()
                elif file_type == 'docx':
                    text_content = self._extract_text_from_docx(file_path)
                    documents = [Document(page_content=text_content, metadata={"source": uploaded_file.name})]
                elif file_type == 'doc':
                    if WORD_SUPPORT:
                        text_content = self._extract_text_from_doc(file_path)
                        documents = [Document(page_content=text_content, metadata={"source": uploaded_file.name})]
                    else:
                        logging.warning(f"Skipping .doc file '{uploaded_file.name}' - win32com not available")
                        continue
                else:
                    logging.warning(f"Unsupported file type: {file_type}")
                    continue  # Skip unsupported file types
                
                # Split documents into chunks
                text_splitter = RecursiveCharacterTextSplitter(
                    chunk_size=500,       # Reduced chunk size for finer granularity
                    chunk_overlap=50,     # Reduced overlap
                    separators=["\n\n", "\n", " ", ""]
                )
                chunks = text_splitter.split_documents(documents)
                # Assign chunk_number per document
                chunk_number = 0
                for chunk in chunks:
                    cleaned_content = self.preprocess_content(chunk.page_content)
                    embedding = self.embeddings.embed_documents([cleaned_content])[0]
                    embedding = np.array(embedding).astype('float32')
                    norm = np.linalg.norm(embedding)
                    if norm == 0:
                        logging.warning("Encountered zero norm embedding. Skipping this chunk.")
                        continue  # Skip embeddings with zero norm to avoid division by zero
                    embedding /= norm  # Normalize to unit vector
                    index.add(np.array([embedding]).astype('float32'))
                    # Generate a unique chunk_id using UUID
                    chunk_id = str(uuid.uuid4())
                    # Extract metadata
                    meta = {
                        "source": uploaded_file.name,
                        "page": chunk.metadata.get("page", None),
                        "chunk_id": chunk_id,  # Unique identifier
                        "chunk_number": chunk_number,  # Position within the document
                        "content": cleaned_content  # Store cleaned content
                    }
                    metadata.append(meta)
                    logging.info(f"Added chunk ID {chunk_id} (Chunk Number: {chunk_number}) from file '{uploaded_file.name}' to the index.")
                    chunk_number += 1
            # Save updated index and metadata
            self.save_faiss_index(db_name, index)
            self.save_metadata(db_name, metadata)
            logging.info(f"Successfully added documents to database: {db_name}")
            return {"success": True}
        except Exception as e:
            error_msg = f"Error adding documents: {str(e)}"
            logging.error(error_msg)
            return {"success": False, "error": error_msg}

    def create_database(self, db_name: str) -> bool:
        """
        Create a new database with the given name.

        Args:
            db_name (str): Name of the database to create.

        Returns:
            bool: True if creation was successful, False otherwise.
        """
        db_path = os.path.join(DATABASES_DIR, db_name)
        if os.path.exists(db_path):
            logging.warning(f"Database '{db_name}' already exists.")
            return False  # Database already exists
        try:
            os.makedirs(db_path)
            logging.info(f"Created directory for database '{db_name}'.")

            # Initialize empty FAISS index with Inner Product (for cosine similarity)
            test_embedding = self.embeddings.embed_query("test")
            test_embedding = np.array(test_embedding).astype('float32')
            norm = np.linalg.norm(test_embedding)
            if norm == 0:
                logging.error("Zero norm encountered during index initialization.")
                return False
            test_embedding /= norm  # Normalize to unit vector
            dimension = test_embedding.shape[0]
            index = faiss.IndexFlatIP(dimension)  # Inner Product for cosine similarity
            faiss.write_index(index, os.path.join(db_path, "faiss.index"))
            logging.info(f"Initialized FAISS index for database '{db_name}' with dimension {dimension}.")

            # Initialize empty metadata and notes
            with open(os.path.join(db_path, "metadata.json"), "w") as f:
                json.dump([], f)
            with open(os.path.join(db_path, "notes.json"), "w") as f:
                json.dump({}, f)
            logging.info(f"Initialized metadata and notes for database '{db_name}'.")
            return True
        except Exception as e:
            logging.error(f"Failed to create database '{db_name}': {e}")
            shutil.rmtree(db_path, ignore_errors=True)
            return False

    def delete_document(self, db_name: str, doc_name: str) -> Dict[str, Any]:
        """
        Delete a specific document from the database.

        Args:
            db_name (str): Name of the database.
            doc_name (str): Name of the document to delete.

        Returns:
            Dict[str, Any]: Result of the operation.
        """
        try:
            db_path = os.path.join(DATABASES_DIR, db_name)
            metadata = self.load_metadata(db_name)
            updated_metadata = [meta for meta in metadata if meta['source'] != doc_name]

            # Save updated metadata
            self.save_metadata(db_name, updated_metadata)

            # Delete the file from the filesystem
            file_path = os.path.join(db_path, os.path.basename(doc_name))
            if os.path.exists(file_path):
                os.remove(file_path)
                logging.info(f"Deleted file '{file_path}'.")
            else:
                logging.warning(f"File '{file_path}' does not exist.")

            # Rebuild the FAISS index if there are remaining documents
            if updated_metadata:
                # Get dimension from existing index
                old_index = self.load_faiss_index(db_name)
                if old_index is None:
                    raise Exception("Could not load existing FAISS index")
                dimension = old_index.d
                
                # Create new index with same dimension
                new_index = faiss.IndexFlatIP(dimension)
                
                # Add embeddings from remaining documents
                for meta in updated_metadata:
                    embedding = self.embeddings.embed_documents([meta['content']])[0]
                    embedding = np.array(embedding).astype('float32')
                    norm = np.linalg.norm(embedding)
                    if norm == 0:
                        logging.warning("Encountered zero norm embedding. Skipping this chunk.")
                        continue
                    embedding /= norm
                    new_index.add(np.array([embedding]).astype('float32'))
                
                self.save_faiss_index(db_name, new_index)
            else:
                # If no documents left, create empty index with correct dimension
                test_embedding = self.embeddings.embed_query("test")
                dimension = len(test_embedding)
                empty_index = faiss.IndexFlatIP(dimension)
                self.save_faiss_index(db_name, empty_index)
            
            logging.info(f"Successfully deleted document '{doc_name}' and rebuilt index.")
            return {"success": True}
        except Exception as e:
            error_msg = f"Failed to delete document: {str(e)}"
            logging.error(error_msg)
            return {"success": False, "error": error_msg}

    def delete_database(self, db_name: str) -> Dict[str, Any]:
        """
        Delete an entire database, including all its documents, metadata, and indexes.

        Args:
            db_name (str): Name of the database to delete.

        Returns:
            Dict[str, Any]: Result of the operation.
        """
        try:
            db_path = os.path.join(DATABASES_DIR, db_name)
            if not os.path.exists(db_path):
                error_msg = f"Database '{db_name}' does not exist."
                logging.error(error_msg)
                return {"success": False, "error": error_msg}

            # Remove the entire database directory
            shutil.rmtree(db_path)
            logging.info(f"Deleted database '{db_name}' successfully.")
            return {"success": True}
        except Exception as e:
            error_msg = f"Failed to delete database '{db_name}': {e}"
            logging.error(error_msg)
            return {"success": False, "error": error_msg}

    def list_databases(self) -> List[str]:
        """
        List all available databases.

        Returns:
            List[str]: List of database names.
        """
        try:
            dbs = [name for name in os.listdir(DATABASES_DIR)
                   if os.path.isdir(os.path.join(DATABASES_DIR, name))]
            logging.info(f"Listed databases: {dbs}")
            return dbs
        except Exception as e:
            logging.error(f"Failed to list databases: {e}")
            return []

    def list_documents(self, db_name: str) -> List[str]:
        """
        List all documents in the specified database.

        Args:
            db_name (str): Name of the database.

        Returns:
            List[str]: List of document names.
        """
        try:
            metadata = self.load_metadata(db_name)
            documents = list({meta.get('source') for meta in metadata})
            logging.info(f"Listed documents for database '{db_name}': {documents}")
            return documents
        except Exception as e:
            logging.error(f"Error listing documents: {e}")
            return []

    def load_faiss_index(self, db_name: str) -> faiss.Index:
        """
        Load the FAISS index for the specified database.

        Args:
            db_name (str): Name of the database.

        Returns:
            faiss.Index: Loaded FAISS index.
        """
        index_path = os.path.join(DATABASES_DIR, db_name, "faiss.index")
        if not os.path.exists(index_path):
            logging.warning(f"FAISS index not found for database '{db_name}'.")
            return None
        try:
            index = faiss.read_index(index_path)
            logging.info(f"Loaded FAISS index for database '{db_name}'.")
            return index
        except Exception as e:
            logging.error(f"Failed to load FAISS index for database '{db_name}': {e}")
            return None

    def save_faiss_index(self, db_name: str, index: faiss.Index):
        """
        Save the FAISS index for the specified database.

        Args:
            db_name (str): Name of the database.
            index (faiss.Index): FAISS index to save.
        """
        index_path = os.path.join(DATABASES_DIR, db_name, "faiss.index")
        try:
            faiss.write_index(index, index_path)
            logging.info(f"Saved FAISS index for database '{db_name}'.")
        except Exception as e:
            logging.error(f"Failed to save FAISS index for database '{db_name}': {e}")

    def load_metadata(self, db_name: str) -> List[Dict[str, Any]]:
        """
        Load metadata for the specified database.

        Args:
            db_name (str): Name of the database.

        Returns:
            List[Dict[str, Any]]: List of metadata dictionaries.
        """
        metadata_path = os.path.join(DATABASES_DIR, db_name, "metadata.json")
        if not os.path.exists(metadata_path):
            logging.warning(f"Metadata file not found for database '{db_name}'.")
            return []
        try:
            with open(metadata_path, "r") as f:
                metadata = json.load(f)
            logging.info(f"Loaded metadata for database '{db_name}'.")
            return metadata
        except Exception as e:
            logging.error(f"Failed to load metadata for database '{db_name}': {e}")
            return []

    def save_metadata(self, db_name: str, metadata: List[Dict[str, Any]]):
        """
        Save metadata for the specified database.

        Args:
            db_name (str): Name of the database.
            metadata (List[Dict[str, Any]]): List of metadata dictionaries.
        """
        metadata_path = os.path.join(DATABASES_DIR, db_name, "metadata.json")
        try:
            with open(metadata_path, "w") as f:
                json.dump(metadata, f, indent=2)
            logging.info(f"Saved metadata for database '{db_name}'.")
        except Exception as e:
            logging.error(f"Failed to save metadata for database '{db_name}': {e}")

    def load_notes(self, db_name: str) -> Dict[str, str]:
        """
        Load notes for the specified database.

        Args:
            db_name (str): Name of the database.

        Returns:
            Dict[str, str]: Dictionary of notes.
        """
        notes_path = os.path.join(DATABASES_DIR, db_name, "notes.json")
        if not os.path.exists(notes_path):
            logging.warning(f"Notes file not found for database '{db_name}'.")
            return {}
        try:
            with open(notes_path, "r") as f:
                notes = json.load(f)
            logging.info(f"Loaded notes for database '{db_name}'.")
            return notes
        except Exception as e:
            logging.error(f"Failed to load notes for database '{db_name}': {e}")
            return {}

    def save_notes(self, db_name: str, notes: Dict[str, str]):
        """
        Save notes for the specified database.

        Args:
            db_name (str): Name of the database.
            notes (Dict[str, str]): Dictionary of notes.
        """
        notes_path = os.path.join(DATABASES_DIR, db_name, "notes.json")
        try:
            with open(notes_path, "w") as f:
                json.dump(notes, f, indent=2)
            logging.info(f"Saved notes for database '{db_name}'.")
        except Exception as e:
            logging.error(f"Failed to save notes for database '{db_name}': {e}")

    def search(self, db_name: str, query: str, top_k: int =10) -> List[Dict[str, Any]]:
        """
        Search the database for the given query.

        Args:
            db_name (str): Name of the database.
            query (str): Search query.
            top_k (int, optional): Number of top results to return. Defaults to 10.

        Returns:
            List[Dict[str, Any]]: List of search results with enhanced context.
        """
        try:
            logging.debug(f"Performing search in database '{db_name}' for query: {query}")
            index = self.load_faiss_index(db_name)
            if index is None:
                logging.error(f"FAISS index not found for database '{db_name}'.")
                return []
            metadata = self.load_metadata(db_name)
            if not metadata:
                logging.info(f"No metadata found for database '{db_name}'.")
                return []
            query_embedding = self.embeddings.embed_query(query)
            query_embedding = np.array(query_embedding).astype('float32')
            norm = np.linalg.norm(query_embedding)
            if norm == 0:
                logging.warning("Encountered zero norm query embedding. Returning no results.")
                return []
            query_embedding /= norm  # Normalize to unit vector
            D, I = index.search(np.array([query_embedding]).astype('float32'), top_k)
            results = []
            seen_chunk_ids = set()
            for score, idx in zip(D[0], I[0]):
                if idx < len(metadata):
                    chunk = metadata[idx]
                    if chunk['chunk_id'] not in seen_chunk_ids:
                        # Attach similarity score
                        chunk_copy = chunk.copy()
                        chunk_copy['similarity'] = float(score)  # Convert numpy float to Python float
                        results.append(chunk_copy)
                        seen_chunk_ids.add(chunk['chunk_id'])
            # Now, for each result, retrieve adjacent chunks
            enhanced_results = []
            for result in results:
                source = result['source']
                chunk_number = result['chunk_number']
                # Find previous chunk
                previous_chunk = next((meta for meta in metadata if meta['source'] == source and meta['chunk_number'] == chunk_number -1), None)
                # Find next chunk
                next_chunk = next((meta for meta in metadata if meta['source'] == source and meta['chunk_number'] == chunk_number +1), None)
                # Compile enhanced result
                combined_content = ""
                if previous_chunk:
                    combined_content += previous_chunk['content'] + "\n"
                combined_content += result['content']
                if next_chunk:
                    combined_content += "\n" + next_chunk['content']
                enhanced_result = {
                    "source": source,
                    "similarity": result['similarity'],
                    "content": combined_content  # Combined content for more context
                }
                enhanced_results.append(enhanced_result)
                logging.info(f"Enhanced result for chunk ID {result['chunk_id']} with adjacent chunks.")
            logging.info(f"Search completed for query '{query}' in database '{db_name}'. Found {len(enhanced_results)} enhanced results.")
            return enhanced_results
        except Exception as e:
            logging.error(f"Error during search: {e}")
            return []
    
    def add_note(self, db_name: str, chunk_id: str, note: str):
        """
        Add or update a note for a specific chunk.

        Args:
            db_name (str): Name of the database.
            chunk_id (str): ID of the chunk.
            note (str): Note content.
        """
        try:
            notes = self.load_notes(db_name)
            notes[chunk_id] = note
            self.save_notes(db_name, notes)
            logging.info(f"Added/Updated note for chunk ID {chunk_id} in database '{db_name}'.")
        except Exception as e:
            logging.error(f"Error adding note: {e}")

    def get_note(self, db_name: str, chunk_id: str) -> str:
        """
        Retrieve a note for a specific chunk.

        Args:
            db_name (str): Name of the database.
            chunk_id (str): ID of the chunk.

        Returns:
            str: Note content.
        """
        try:
            notes = self.load_notes(db_name)
            note = notes.get(chunk_id, "")
            logging.info(f"Retrieved note for chunk ID {chunk_id} in database '{db_name}'.")
            return note
        except Exception as e:
            logging.error(f"Error getting note: {e}")
            return ""
