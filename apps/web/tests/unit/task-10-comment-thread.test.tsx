// @vitest-environment jsdom

import React from "react";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { CommentThread } from "../../src/features/collaboration/CommentThread";

afterEach(cleanup);

describe("CommentThread authoritative submission", () => {
  it("preserves comment input when a stale conflict rejects the command", async () => {
    const error = Object.assign(new Error("The item changed."), {
      code: "conflict_stale_version",
      requestId: "request-1",
      retryable: false,
    });
    const onAddComment = vi.fn(async () => {
      throw error;
    });
    const user = userEvent.setup();

    render(<CommentThread comments={[]} onAddComment={onAddComment} />);
    const input = screen.getByTestId("comment-input");
    await user.type(input, "Please preserve this review note.");
    await user.click(screen.getByTestId("post-comment-btn"));

    expect(onAddComment).toHaveBeenCalledWith(
      "Please preserve this review note.",
      [],
    );
    expect((input as HTMLTextAreaElement).value).toBe("Please preserve this review note.");
    expect(screen.getByRole("alert").textContent).toContain("item changed");
  });
});



describe("CommentThread persisted history", () => {
  it("renders attributable revisions and mention recipients from the detail projection", () => {
    render(
      <CommentThread
        comments={[
          {
            commentId: "comment-1",
            authorId: "actor-1",
            replyDepth: 0,
            createdAt: "2026-09-06T00:00:00Z",
            revisions: [
              {
                revisionId: "revision-1",
                ordinal: 1,
                authorId: "actor-1",
                body: "Original review note.",
                createdAt: "2026-09-06T00:00:00Z",
                mentionRecipientIds: ["member-2"],
              },
              {
                revisionId: "revision-2",
                ordinal: 2,
                authorId: "actor-1",
                body: "Corrected review note.",
                createdAt: "2026-09-06T01:00:00Z",
                mentionRecipientIds: ["member-3"],
              },
            ],
          },
        ]}
      />,
    );

    expect(screen.getByText("Original review note.")).toBeTruthy();
    expect(screen.getByText("Corrected review note.")).toBeTruthy();
    expect(screen.getByText(/member-2/)).toBeTruthy();
    expect(screen.getByText(/member-3/)).toBeTruthy();
  });
});



describe("CommentThread authoritative replies", () => {
  it("preserves reply input when the command is rejected", async () => {
    const onReply = vi.fn(async () => {
      throw new Error("The reply is stale.");
    });
    const user = userEvent.setup();

    render(
      <CommentThread
        comments={[
          {
            commentId: "comment-1",
            authorId: "actor-1",
            replyDepth: 0,
            createdAt: "2026-09-06T00:00:00Z",
            revisions: [
              {
                revisionId: "revision-1",
                ordinal: 1,
                authorId: "actor-1",
                body: "Please review this source.",
                createdAt: "2026-09-06T00:00:00Z",
                mentionRecipientIds: [],
              },
            ],
          },
        ]}
        onReply={onReply}
      />,
    );

    const input = screen.getByLabelText("Reply to comment comment-1");
    await user.type(input, "The source remains inconclusive.");
    await user.click(screen.getByRole("button", { name: "Post Reply" }));

    expect(onReply).toHaveBeenCalledWith(
      "comment-1",
      "The source remains inconclusive.",
      [],
    );
    expect((input as HTMLTextAreaElement).value).toBe(
      "The source remains inconclusive.",
    );
    expect(screen.getByRole("alert").textContent).toContain("stale");
  });
});



describe("CommentThread authoritative revisions", () => {
  it("preserves revised content when the command is rejected", async () => {
    const onRevise = vi.fn(async () => {
      throw new Error("The revision is stale.");
    });
    const user = userEvent.setup();

    render(
      <CommentThread
        comments={[
          {
            commentId: "comment-1",
            authorId: "actor-1",
            replyDepth: 0,
            createdAt: "2026-09-06T00:00:00Z",
            revisions: [
              {
                revisionId: "revision-1",
                ordinal: 1,
                authorId: "actor-1",
                body: "Original review note.",
                createdAt: "2026-09-06T00:00:00Z",
                mentionRecipientIds: [],
              },
            ],
          },
        ]}
        onRevise={onRevise}
      />,
    );

    const input = screen.getByLabelText("Revise comment comment-1");
    await user.clear(input);
    await user.type(input, "Corrected review note.");
    await user.click(screen.getByRole("button", { name: "Save Revision" }));

    expect(onRevise).toHaveBeenCalledWith(
      "comment-1",
      "Corrected review note.",
      [],
    );
    expect((input as HTMLTextAreaElement).value).toBe("Corrected review note.");
    expect(screen.getByRole("alert").textContent).toContain("stale");
  });
});
