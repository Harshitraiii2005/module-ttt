# Text-To-Tree (TTT)

### Vectorless, Search & Retrieval - at 1/10th token consumption
TTT navigates your document structure, and retrieves only the sections needed to answer your query before invoking your LLM. 

Every answer is grounded in the source document, using up to 90% fewer LLM tokens than conventional approaches.

## See the Difference
TTT was benchmarked against OpenAI's managed File Search implementation using GPT-4o across representative enterprise document types.

| **Document** | **Total Queries** | **Avg. Tokens / Query (OpenAI + Vector DB)** | **Avg. Tokens / Query (TTT)** | **Total Tokens Saved** | **Token Reduction** |
|:-------------|------------------:|---------------------------------------------:|------------------------------:|-----------------------:|--------------------:|
| Microsoft FY2025 Annual Report | 27 | 17.38k | 850 | 446.26k | **95.11%** |
| Apple FY2024 Annual Report | 25 | 16.44k | 1,196 | 381.17k | **92.72%** |
| OECD Economic Outlook | 22 | 15.83k | 2,479 | 293.75k | **84.34%** |
| WHO Health Equity Report | 19 | 15.39k | 1,140 | 270.73k | **92.60%** |
| **Total** | **93** | **16.36k** | **1,388** | **1,392k** | **91.52%** |

## See it in Action : 
Experience a document assistant chatbot powered with ❤️ using TTT.<br> 
Upload your own document or explore one of our samples and ask questions naturally. Every answer is backed by our structure aware retrieval engine that navigates your document before the LLM generates a response.<br>
See TTT in action through our AI document chatbot. Upload your document or explore one of our samples and ask questions naturally. Every answer is backed by the exact document section retrieval before the LLM generated a response.

[chat.talkingdb.io](https://chat.talkingdb.io/)

## How TTT Thinks :

Conventional chunking strategies can split tables, lists, headings, and other related content across multiple chunks, losing document structure. During retrieval often returning multiple partially relevant chunks, increasing irrelevant context and LLM token consumption.
TTT powers retrieval differently. It transforms documents into a Document Tree that preserves their structural hierarchy and connects sections, subsections, tables, figures, and other elements. When a query arrives, TTT navigates this structure to retrieve only the relevant document sections before invoking the LLM.
The result is a vectorless, structure aware retrieval engine that preserves document context, reduces unnecessary LLM input, and significantly lowers token consumption while maintaining accurate responses.

Getting started

Ready to build with TTT? Get the service running locally in minutes, explore the APIs, and submit your first document. 
Quick start:
Pull and run the latest image:
docker run -it -p 8090:8090 talkingdb/ttt

Once the container is running:

API Base URL: http://localhost:8090 
Swagger Documentation: http://localhost:8090/docs 

Try Talkingdb → Installation, Docker setup, Swagger UI, your first document upload, and first query.

Documentation 
Looking for more? 
Getting Started - Installation, configuration, and your first end-to-end query.
API Reference - Endpoints, request/response models, and examples.
Architecture - Document Tree construction, indexing, and retrieval internals.
Deployment Guides - Production deployment and infrastructure.
Linked repositories
TTT is one service inside the broader TalkingDB platform. It depends on, and works alongside, these repositories:
Repository
Role
base-tdb-models
Shared Pydantic/data models used across all TalkingDB services (jobs, documents, metadata, API responses).
base-tdb-helpers
Shared utility layer — storage clients, auth, graph helpers, validation.
base-tdb-clients
Thin client wrappers for external dependencies (SQLite) used throughout the platform.
package-content-elementizer
Parses raw documents (PDF, DOCX, and more) into structured elements — the first step in building a TTT tree.
infra-tdb-platform
Infrastructure-as-code for the platform's cloud footprint — VMs, networking, DNS.


Contributing
Interested in contributing to TTT? 
See the contributor guide for local development, DevPod setup, and troubleshooting.
Get in touch

Looking to bring TTT into your own stack and cut down what you're spending on document search and retrieval? Talk to us. We'll help you figure out what that could look like for your team.
hello@talkingdb.io 
https://talkingdb.io/
Try TalkingDB
Linkedin

