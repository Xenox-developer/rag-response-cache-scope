Does a tenant-aware key make a RAG answer cache permission-aware?

I tested three policies in a local cache prototype: query-only lookup; tenant + query lookup; and fresh source authorization before lookup, with a key bound to the allowed document’s ID, version and content.

The matrix had 144 request sequences: eight synthetic fixtures × six scenarios × three policies. Source access was checked correctly on every cache miss. The first two policies returned cached answers before checking the current caller’s source access.

Unauthorized final answers across 24 access-control sequences per policy:
• Query only: 24/24.
• Tenant + query: 16/24.
• Fresh authorized context: 0/24.

The tenant key stopped cross-tenant reuse: 0/8 unauthorized answers there. It still returned the warmed answer to a reader without access in 8/8 cases, and after the original caller’s access was revoked in 8/8.

Freshness was a separate failure. After a source update, both simpler policies returned the old answer in 8/8 cases; the context policy did so in 0/8. All three policies produced valid cache hits in 8/8 authorized repeat controls and correct denials in 8/8 cold-denial controls.

The context policy changes both authorization timing and cache scope. This is not evidence that changing a key alone handles revocation. It assumes a fresh, authoritative view of permissions and sources before serving a hit.

I used INVARIANT for implementation, eight fixed acceptance checks and implementation review. A separate auditor checked the recorded state transitions across all 144 sequences and the frozen inputs.

These are selected deterministic counterexamples in an in-memory prototype. Answers were synthetic stand-ins: no measured LLM calls, semantic matching, distributed revocation races or deployed products were tested. The counts are not incident rates.

Code, protocol, raw states and chart:
https://github.com/Xenox-developer/rag-response-cache-scope

INVARIANT:
https://github.com/Xenox-developer/invariant

Primary documentation:
https://learn.microsoft.com/en-us/azure/api-management/llm-semantic-cache-lookup-policy
https://learn.microsoft.com/en-us/azure/search/search-document-level-access-overview
