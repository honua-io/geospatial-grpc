# Native attachments over gRPC-Web

Applications discover attachment capabilities and limits through `DescribeLayer`.
All attachment operations use unary calls, including large uploads. Download
bytes come from a short-lived signed URL returned after an authorized RPC.
The protocol supports browser gRPC-Web without client streaming.

An attachment parent names a service, layer and exactly one object or global ID.
The server resolves that identity through the same canonical resource and access
policy as feature operations. Listing and download require read access; upload,
replacement and deletion require edit access to the parent feature. Every session
operation rechecks access. A session identifier alone grants no access.

## Small uploads

Send `UploadAttachment` with metadata and complete bytes when the file fits the
advertised unary limit. The declared size must be nonnegative and equal the
content length. SHA-256 is required and must match. Zero-byte files are permitted
by the protocol, subject to the server's content validation policy.

An absent replacement ID creates an attachment. A present positive ID atomically
replaces that attachment on the same parent, preserving its identity. The old
content remains available until validation and publication succeed. Names are
display names, never storage paths. Servers enforce allowed content types, scan
policy, attachment count and aggregate byte limits before publication.

## Large uploads

1. Call `BeginAttachmentUpload` with complete metadata and a fresh idempotency key.
2. Send `UploadAttachmentChunk` calls in order using the returned session ID,
   `next_offset_bytes` and `max_chunk_bytes`. Each nonempty chunk has its own SHA-256.
3. Call `CommitAttachmentUpload` when the accepted length equals the declared size.
4. Call `AbortAttachmentUpload` to discard an unfinished upload.

The server accepts only the exact next offset. Replaying an accepted chunk with
identical bytes succeeds and returns the current offset; a gap or conflicting
replay fails `FAILED_PRECONDITION` without changing content. Retrying begin with
the same metadata and key returns the session's current offset, including after
a lost chunk response. A changed request using the same key fails
`ALREADY_EXISTS`. Clients never infer accepted bytes from a transport failure.

Sessions have a fixed bounded expiry reported by the server. Servers persist
accepted chunks and session state across process restarts and share that state
across serving instances. Expired temporary data is reclaimed. Expiry fails
`NOT_FOUND`; the client begins a new logical upload with a new key. Abort is
idempotent for the owning caller, including after expiry, and never deletes a
committed attachment. Empty chunks and chunks beyond the declared size fail
`INVALID_ARGUMENT`.

Commit verifies total length, complete digest, content policy, current parent
existence, access and quotas before atomic publication. Partial content is never
listed or downloadable. Commit retries return the same attachment throughout the
session lifetime. Failed validation leaves existing attachment content intact.
Concurrent quota checks and publication must serialize to avoid exceeding limits.

## Retry and download rules

Creation, replacement, begin and deletion keys are scoped to the authenticated
caller, parent and operation. Identical retries return the original outcome;
conflicting payloads fail `ALREADY_EXISTS`. Servers retain outcomes at least
through the advertised session expiry for session operations and document their
bounded unary/deletion retention window. Clients reuse a key only for retries of
one logical operation.

`GetAttachmentUrl` returns an HTTPS URL, expiry and attachment metadata. The URL
is a bearer credential limited to one attachment and download operation. It must
expire no later than the reported instant. Clients must not persist or log it.
They request another authorized URL after expiry. Servers may proxy local storage
through a signed endpoint; applications do not need storage-provider credentials.
Authorization changes prevent new grants; an issued grant can remain usable until
its short expiry. Responses carrying grants must prevent intermediary caching.

`ListAttachments` uses bounded paging. Continuation tokens bind the parent,
filters and caller, and each page rechecks authorization. Inaccessible metadata
must not leak through counts or cursors. Listing does not return signed URLs.

This replaces the client-streaming attachment direction described in issue #43.
The separate time-filter and grouped-statistics facets of that issue are unchanged.
