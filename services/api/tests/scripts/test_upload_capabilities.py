import pytest
import uuid6
from clearcut.scripts.adapters.in_memory_storage import InMemoryObjectStorage
from clearcut.scripts.application.upload_service import UploadService
from clearcut.scripts.domain.artifacts import (
    validate_screenplay_magic_bytes,
)


@pytest.mark.asyncio
async def test_upload_capability_and_finalization():
    storage = InMemoryObjectStorage()
    service = UploadService(storage=storage)

    org_id = uuid6.uuid7()
    project_id = uuid6.uuid7()
    actor_id = uuid6.uuid7()

    # Create upload capability
    capability, upload_url = await service.create_upload_capability(
        org_id=org_id,
        project_id=project_id,
        actor_id=actor_id,
        filename="screenplay_draft.fountain",
        content_type="text/plain"
    )

    assert capability.org_id == org_id
    assert capability.project_id == project_id
    assert capability.is_valid()

    # Finalize upload with valid Fountain content
    raw_content = b"EXT. BRICK MANSION - NIGHT\n\nJOHN walks into the room."
    artifact = await service.finalize_upload(
        org_id=org_id,
        project_id=project_id,
        actor_id=actor_id,
        capability_id=capability.capability_id,
        data=raw_content
    )

    assert artifact.status == "finalized"
    assert artifact.size_bytes == len(raw_content)
    assert artifact.sha256_hash is not None
    assert artifact.filename == "screenplay_draft.fountain"

    # Stored in storage
    stored = await storage.get_object(artifact.storage_path)
    assert stored == raw_content

@pytest.mark.asyncio
async def test_magic_bytes_validation():
    # PDF magic bytes
    pdf_bytes = b"%PDF-1.4\n1 0 obj\n..."
    assert validate_screenplay_magic_bytes(pdf_bytes, "application/pdf", "draft.pdf") is True

    # Spoofed PDF (EXE binary masquerading as PDF)
    fake_pdf = b"MZ\x90\x00\x03\x00\x00\x00"
    assert validate_screenplay_magic_bytes(fake_pdf, "application/pdf", "draft.pdf") is False

    # FDX magic bytes
    fdx_bytes = b"<?xml version=\"1.0\" encoding=\"UTF-8\"?><FinalDraft DocumentType=\"Script\">"
    assert validate_screenplay_magic_bytes(fdx_bytes, "application/xml", "draft.fdx") is True
