#!/usr/bin/env python3
import chromadb
from sentence_transformers import SentenceTransformer
import json
import argparse
import os
import sys
from typing import List, Dict, Any

class JSONLEmbedder:
    def __init__(self, persist_directory: str = "./chroma_db"):

        #Start JSONL embedder
        # persist_directory: Path to ChromaDB database
    
        self.persist_directory = persist_directory
        self.client = chromadb.PersistentClient(path=persist_directory)
        self.embedder = SentenceTransformer("BAAI/bge-m3")
        self.collection = None
        
    def create_collection(self, collection_name: str = "documents"):
        #Create or get chromadb
        try:
            self.collection = self.client.get_collection(collection_name)
            print(f"Using existing collection: {collection_name}")
        except:
            self.collection = self.client.create_collection(
                name=collection_name,
                metadata={"description": "Document chunks with BGE-M3 embeddings"}
            )
            print(f"Created new collection: {collection_name}")
        
        return self.collection
    
    #Important 1
    def load_chunks_from_jsonl(self, jsonl_file: str) -> List[Dict]:
        """
        Load chunks from JSONL file
        
        Args:
            jsonl_file: Path to JSONL file with chunks
            
        Returns:
            List of chunks with metadata
        """
        if not os.path.exists(jsonl_file):
            raise FileNotFoundError(f"JSONL file not found: {jsonl_file}")
        
        print(f"Loading chunks from: {os.path.basename(jsonl_file)}")
        
        chunks = []
        with open(jsonl_file, 'r', encoding='utf-8') as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if line:
                    try:
                        chunk = json.loads(line)
                        chunks.append(chunk)
                    except json.JSONDecodeError as e:
                        print(f"Error parsing line {line_num}: {e}")
                        continue
        
        print(f"Loaded {len(chunks)} chunks from JSONL")
        return chunks
    
    #Important 2
    
    def prepare_embeddings(self, chunks: List[Dict], jsonl_file: str) -> tuple:
        """
        Prepare documents and generate embeddings from JSONL chunks
        
        Args:
            chunks: List of chunks from JSONL
            jsonl_file: Source JSONL file name
            
        Returns:
            Tuple of (documents, metadatas, ids, embeddings)
        """
        documents = []
        metadatas = []
        ids = []
        
        print("Preparing embeddings from JSONL chunks...")
        
        for i, chunk in enumerate(chunks):
            # Extract text content from various possible field names
            text_content = ""
            if 'text' in chunk:
                text_content = chunk['text']
            elif 'content' in chunk:
                text_content = chunk['content']
            elif 'page_text' in chunk:
                text_content = chunk['page_text']
            else:
                # Try to find any text field
                text_candidates = [v for v in chunk.values() if isinstance(v, str)]
                text_content = max(text_candidates, key=len) if text_candidates else ""
                
            if not text_content.strip():
                print(f"Skipping chunk {i+1}: No text content found")
                continue
            
            documents.append(text_content)
            
           # Build comprehensive metadata
            base_name = os.path.basename(jsonl_file)

            # Normalize document name: remove "_chunks.jsonl"
            doc_name = base_name.replace("_chunks.jsonl", "").replace(".jsonl", "")
            chunk_number = i + 1

            metadata = {
                'chunk_id': f"{doc_name}_page_{chunk_number}",

                # Page information
                'page_number': chunk.get('page_number', chunk.get('page', 0)),
                'total_pages': chunk.get('total_pages', chunk.get('num_pages', 0)),

                # FIXED source file metadata
                'source_file': doc_name,
                'document': doc_name,    # <--- Add this so RAG clearly knows document source

                # Other metadata
                'doc_type': chunk.get('doc_type', chunk.get('type', 'pdf')),
                'chunk_size': len(text_content),

                # JSONL file source
                'jsonl_source': base_name
            }

            
            # Add any additional metadata from the chunk
            for key, value in chunk.items():
                if key not in ['text', 'content', 'page_text'] and isinstance(value, (str, int, float, bool)):
                    if key not in metadata:  # Don't overwrite existing keys
                        metadata[key] = value
            
            metadatas.append(metadata)
            unique_id = metadata['chunk_id']
            ids.append(unique_id)
        
        #------To Sentence Transformenr (BGE-m3)-------

        
        # Generate embeddings
        print(f"Generating embeddings for {len(documents)} chunks...")
        embeddings = self.embedder.encode(documents).tolist()
        
        return documents, metadatas, ids, embeddings
    
    #Important 3
    def store_in_chromadb(self, documents: List[str], metadatas: List[Dict], 
                         ids: List[str], embeddings: List[List[float]], 
                         collection_name: str = "documents"):
        """Store documents with embeddings in ChromaDB"""
        self.create_collection(collection_name)
        
        print(f"Storing in ChromaDB collection: {collection_name}")
        
        # Store in batches to avoid memory issues
        batch_size = 100
        total_stored = 0
        
        for i in range(0, len(documents), batch_size):
            end_idx = min(i + batch_size, len(documents))
            batch_docs = documents[i:end_idx]
            batch_metas = metadatas[i:end_idx]
            batch_ids = ids[i:end_idx]
            batch_embeds = embeddings[i:end_idx]
            
            self.collection.add(
                embeddings=batch_embeds,
                documents=batch_docs,
                metadatas=batch_metas,
                ids=batch_ids
            )
            
            total_stored += len(batch_docs)
            print(f"   Stored batch {i//batch_size + 1}: {len(batch_docs)} chunks")
        
        print(f"Successfully stored {total_stored} chunks in ChromaDB")
    
    def embed_jsonl(self, jsonl_file: str, collection_name: str = "documents"):
        """
        Complete JSONL embedding pipeline
        
        Args:
            jsonl_file: Path to JSONL file with chunks
            collection_name: ChromaDB collection name
            
        Returns:
            Number of chunks embedded
        """
        # Load chunks from JSONL
        chunks = self.load_chunks_from_jsonl(jsonl_file)
        
        if not chunks:
            print("No chunks loaded from JSONL file")
            return 0
        
        # Prepare embeddings
        documents, metadatas, ids, embeddings = self.prepare_embeddings(chunks, jsonl_file)
        
        if not documents:
            print("No valid documents to embed")
            return 0
        
        # Store in ChromaDB
        self.store_in_chromadb(documents, metadatas, ids, embeddings, collection_name)
        
        return len(documents)
    
    def get_collection_stats(self, collection_name: str = None):
        """Get statistics about a collection"""
        if collection_name:
            try:
                collection = self.client.get_collection(collection_name)
                self.collection = collection
            except:
                return f"Collection '{collection_name}' not found"
        
        if not self.collection:
            return "No collection loaded"
        
        count = self.collection.count()
        
        # Get sample metadata for analysis
        sample = self.collection.get(limit=min(100, count))
        sources = {}
        doc_types = {}
        
        if sample['metadatas']:
            for metadata in sample['metadatas']:
                source = metadata.get('source_file', 'unknown')
                sources[source] = sources.get(source, 0) + 1
                
                doc_type = metadata.get('doc_type', 'unknown')
                doc_types[doc_type] = doc_types.get(doc_type, 0) + 1
        
        stats = {
            'total_chunks': count,
            'sources': sources,
            'doc_types': doc_types,
            'collection_name': self.collection.name,
            'db_path': self.persist_directory
        }
        
        return stats

def main():
    parser = argparse.ArgumentParser(
        description='Embed JSONL chunks into ChromaDB with BGE-M3',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
Examples:
  # Embed JSONL file into ChromaDB (default collection: documents)
  python embed_jsonl.py -i chunks.jsonl
  
  # Embed with custom database location
  python embed_jsonl.py -i chunks.jsonl -d ./my_chroma_db
  
  # Show collection statistics
  python embed_jsonl.py -s
  
  # Show specific collection statistics
  python embed_jsonl.py -s --collection pdf_documents
  
  # List all collections
  python embed_jsonl.py -l
  
  # Embed multiple JSONL files
  python embed_jsonl.py -i chunks1.jsonl -i chunks2.jsonl
  
  # Clear collection before embedding
  python embed_jsonl.py -i chunks.jsonl -c
        '''
    )
    
    # Input options
    parser.add_argument('-i', '--input', action='append', help='Input JSONL file(s) to embed (can use multiple times)')
    parser.add_argument('--collection', default='documents', help='Collection name (default: documents)')
    parser.add_argument('-d', '--db-dir', default='./chroma_db', help='ChromaDB directory (default: ./chroma_db)')
    
    # Operation options
    parser.add_argument('-s', '--stats', action='store_true', help='Show collection statistics')
    parser.add_argument('-l', '--list', action='store_true', help='List all collections')
    parser.add_argument('-c', '--clear', action='store_true', help='Clear collection before embedding')
    
    args = parser.parse_args()
    
    # Initialize embedder
    print("JSONL to ChromaDB Embedder")
    print("=" * 50)
    embedder = JSONLEmbedder(persist_directory=args.db_dir)
    
    # List collections
    if args.list:
        collections = embedder.client.list_collections()
        if collections:
            print("📚 Available collections:")
            for collection in collections:
                count = collection.count()
                print(f"   • {collection.name} ({count} chunks)")
        else:
            print( "No collections found")
        return
    
    # Show statistics
    if args.stats:
        stats = embedder.get_collection_stats(args.collection)
        if isinstance(stats, dict):
            print(f"\n Collection Statistics: '{args.collection}'")
            print(f"   Total chunks: {stats['total_chunks']}")
            print(f"   Document types: {stats.get('doc_types', {})}")
            print(f"   Sources: {stats.get('sources', {})}")
            print(f"   Database: {stats['db_path']}")
        else:
            print(f" {stats}")
        return
    
    # Clear collection if requested
    if args.clear:
        try:
            embedder.client.delete_collection(args.collection)
            print(f"  Cleared collection: {args.collection}")
        except:
            print(f"Collection '{args.collection}' doesn't exist or couldn't be cleared")
    
    # Process input files
    if args.input:
        total_chunks = 0
        
        for jsonl_file in args.input:
            if not os.path.exists(jsonl_file):
                print(f"JSONL file not found: {jsonl_file}")
                continue
            
            try:
                print(f"\nProcessing: {os.path.basename(jsonl_file)}")
                chunk_count = embedder.embed_jsonl(jsonl_file, args.collection)
                total_chunks += chunk_count
                print(f"Embedded {chunk_count} chunks into '{args.collection}'")
                
            except Exception as e:
                print(f"Error embedding {jsonl_file}: {e}")
        
        if total_chunks > 0:
            print(f"\nCompleted! Total chunks embedded: {total_chunks}")
            
            # Show final statistics
            stats = embedder.get_collection_stats(args.collection)
            if isinstance(stats, dict):
                print(f"Final collection '{args.collection}': {stats['total_chunks']} chunks")
        else:
            print("\nNo chunks were embedded")
    
    else:
        if not args.stats and not args.list:
            print("No input files specified")
            print("\nUse -i to specify input JSONL file(s)")
            parser.print_help()

if __name__ == "__main__":
    main()