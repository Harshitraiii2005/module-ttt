# Text-To-Tree (TTT)

### Vectorless, Search & Retrieval - at 1/10th token consumption
TTT navigates your document structure, and retrieves only the sections needed to answer your query before invoking your LLM. 

Every answer is grounded in the source document, using up to 90% fewer LLM tokens than conventional approaches.

## See the Difference
TTT was benchmarked against OpenAI's managed File Search implementation using GPT-4o across representative enterprise document types.

| **Document** | **Total Queries** | **Avg. Tokens / Query (OpenAI + Vector DB)** | **Avg. Tokens / Query (TTT)** | **Total Tokens Saved** | **Token Reduction** |
|:-------------|------------------:|---------------------------------------------:|------------------------------:|-----------------------:|--------------------:|
| [Microsoft FY2025 Annual Report](https://docs.google.com/document/d/1NRpcdd3_Ua5SM6UzX90w4UhAykgWw6TZ/edit?usp=sharing&ouid=115408291671450200196&rtpof=true&sd=true) | 27 | 17.38k tokens/query | 850 tokens/query | 446.26k | **95.11%** |
| [Apple FY2024 Annual Report](https://drive.google.com/file/d/1QuNqBrls1JUUKxOnMqxZh77niK_YJ0b_/view?usp=sharing) | 25 | 16.44k tokens/query | 1,196 tokens/query | 381.17k | **92.72%** |
| [OECD Economic Outlook](https://drive.google.com/file/d/1_edl_-zSCtnCpHXpQjc6LfA5UQiXo0ac/view?usp=drive_link) | 22 | 15.83k tokens/query| 2,479 tokens/query | 293.75k | **84.34%** |
| [WHO Health Equity Report](https://drive.google.com/file/d/1gDjypJsGdSrxV5lmBcz3e7Q5GLVEyOtm/view?usp=sharing) | 19 | 15.39k tokens/query | 1,140 tokens/query | 270.73k | **92.60%** |
| **Total** | **93** | **16.36k tokens/query** | **1,388 tokens/query** | **1,392k** | **91.52%** |

## See it in Action : 
**Experience a [document assistant chatbot](http://chat.talkingdb.io) powered with ❤️ using TTT.**<br> 
Upload your own document or explore one of our samples and ask questions naturally. Every answer is backed by our structure aware retrieval engine that navigates your document before the LLM generates a response.<br>
See TTT in action through our AI document chatbot. Upload your document or explore one of our samples and ask questions naturally. Every answer is backed by the exact document section retrieval before the LLM generated a response.

[chat.talkingdb.io](https://chat.talkingdb.io/)

## How TTT Thinks :

![image alt](https://github.com/vamsi-a-hash/module-ttt/blob/TAL-966-docs/update-readme/assets/image1.png?raw=true)

Conventional chunking strategies can split tables, lists, headings, and other related content across multiple chunks, losing document structure. During retrieval often returning multiple partially relevant chunks, increasing irrelevant context and LLM token consumption.<br>
TTT powers retrieval differently. It transforms documents into a **Document Tree** that preserves their structural hierarchy and connects sections, subsections, tables, figures, and other elements. When a query arrives, TTT navigates this structure to retrieve only the relevant document sections before invoking the LLM.<br>
The result is a **vectorless, structure aware retrieval engine** that preserves document context, reduces unnecessary LLM input, and significantly lowers token consumption while maintaining accurate responses.

## Getting started

Ready to build with TTT? Get the service running locally in minutes, explore the APIs, and submit your first document.<br>
### Quick start:
Pull and run the latest image:
```
docker run -it -p 8090:8090 talkingdb/ttt
```
Once the container is running:

API Base URL: `http://localhost:8090` <br>
Swagger Documentation: `http://localhost:8090/docs` 

[Try Talkingdb](https://hub.docker.com/r/talkingdb/ttt) → Installation, Docker setup, Swagger UI, your first document upload, and first query.

## Documentation 
Looking for more? <br>
- Getting Started - Installation, configuration, and your first end-to-end query.
- API Reference - Endpoints, request/response models, and examples.
- Architecture - Document Tree construction, indexing, and retrieval internals.
- Deployment Guides - Production deployment and infrastructure.

## Linked repositories
TTT is one service inside the broader TalkingDB platform. It depends on, and works alongside, these repositories:<br>
| **Repository** | **Role** |
|:---------------|:---------|
| [`base-tdb-models`](https://github.com/TalkingDB/base-tdb-models) | Shared Pydantic/data models used across all TalkingDB services (jobs, documents, metadata, API responses). |
| [`base-tdb-helpers`](https://github.com/TalkingDB/base-tdb-helpers) | Shared utility layer — storage clients, auth, graph helpers, validation.|
| [`base-tdb-clients`](https://github.com/TalkingDB/base-tdb-clients) | Thin client wrappers for external dependencies (SQLite) used throughout the platform. |
| [`package-content-elementizer`](https://github.com/TalkingDB/package-content-elementizer) | Parses raw documents (PDF, DOCX, and more) into structured elements — the first step in building a TTT tree. |
| [`infra-tdb-platform`](https://github.com/TalkingDB/infra-tdb-platform) | Infrastructure-as-code for the platform's cloud footprint — VMs, networking, DNS. |


## Contributing
Interested in contributing to TTT? <br>
See the [contributor guide](https://docs.talkingdb.io/doc/guides-ofg1QILxjP) for local development, DevPod setup, and troubleshooting.

## Get in touch
Looking to bring TTT into your own stack and cut down what you're spending on document search and retrieval? Talk to us. We'll help you figure out what that could look like for your team.

[![talkingdb.io](https://img.shields.io/badge/talkingdb.io-4285F4?style=for-the-badge&logo=googlechrome&logoColor=white)](https://talkingdb.io/)
[![Try TalkingDB](https://img.shields.io/badge/Try%20TalkingDB-00C7B7?style=for-the-badge&logo=databricks&logoColor=white)](https://talkingdb.io/)
[![LinkedIn](https://img.shields.io/badge/LinkedIn-0A66C2?style=for-the-badge&logo=linkedin&logoColor=white)](https://www.linkedin.com/company/talkingdb/about/)
[![Book a Demo](https://img.shields.io/badge/Book%20a%20Demo-6E6E6E?style=for-the-badge&logo=googlecalendar&logoColor=white)](mailto:hello@talkingdb.io)
[![Contact Us](https://img.shields.io/badge/Contact%20Us-4285F4?style=for-the-badge&logo=gmail&logoColor=white)](mailto:hello@talkingdb.io)
