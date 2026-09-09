import type { ItemDetailComment, Membership } from "@clearcut/contracts";
import React, { useState } from "react";
import { Badge, Banner, Card } from "../../components/ds";

export type MentionRecipient = Pick<Membership, "userId" | "email" | "role">;

export interface CommentThreadProps {
  comments?: ItemDetailComment[];
  mentionRecipients?: MentionRecipient[];
  onAddComment?: (content: string, mentionRecipientIds: string[]) => Promise<void>;
  onReply?: (
    commentId: string,
    content: string,
    mentionRecipientIds: string[],
  ) => Promise<void>;
  onRevise?: (
    commentId: string,
    content: string,
    mentionRecipientIds: string[],
  ) => Promise<void>;
}

interface MentionSelectorProps {
  id: string;
  label: string;
  recipients: MentionRecipient[];
  selectedIds: string[];
  onChange: (recipientIds: string[]) => void;
}

/**
 * The label stays a sibling of the select: a wrapping <label> folds the selected
 * options' text into the control's accessible name.
 */
function MentionSelector({ id, label, recipients, selectedIds, onChange }: MentionSelectorProps) {
  return (
    <div className="field">
      <label className="field-label" htmlFor={id}>
        {label}
      </label>
      <select
        id={id}
        multiple
        value={selectedIds}
        onChange={(event) =>
          onChange(Array.from(event.currentTarget.selectedOptions, (option) => option.value))
        }
      >
        {recipients.map((recipient) => (
          <option key={recipient.userId} value={recipient.userId}>
            {recipient.email ?? recipient.userId} ({recipient.role})
          </option>
        ))}
      </select>
      <span className="field-hint">
        Select only active members authorized for this project.
      </span>
    </div>
  );
}

interface CommentReplyFormProps {
  commentId: string;
  mentionRecipients: MentionRecipient[];
  onReply: NonNullable<CommentThreadProps["onReply"]>;
}

function CommentReplyForm({ commentId, mentionRecipients, onReply }: CommentReplyFormProps) {
  const [content, setContent] = useState("");
  const [mentionRecipientIds, setMentionRecipientIds] = useState<string[]>([]);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    const trimmedContent = content.trim();
    if (!trimmedContent) return;

    const submittedMentions = mentionRecipientIds;
    setSubmitting(true);
    setError(null);
    // Same reasoning as the root comment form: clear before awaiting so the
    // draft never duplicates the posted reply, and restore on failure.
    setContent("");
    setMentionRecipientIds([]);
    try {
      await onReply(commentId, trimmedContent, submittedMentions);
    } catch (submissionError) {
      setContent(trimmedContent);
      setMentionRecipientIds(submittedMentions);
      setError(
        submissionError instanceof Error ? submissionError.message : "The reply was not recorded.",
      );
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <form onSubmit={handleSubmit} className="stack-sm gap-t-4">
      <div className="divider" />
      <label className="sr-only" htmlFor={`reply-${commentId}`}>
        Reply to comment {commentId}
      </label>
      <textarea
        id={`reply-${commentId}`}
        rows={2}
        value={content}
        onChange={(event) => setContent(event.target.value)}
      />
      <MentionSelector
        id={`reply-mentions-${commentId}`}
        label={`Mention team members for reply to comment ${commentId}`}
        recipients={mentionRecipients}
        selectedIds={mentionRecipientIds}
        onChange={setMentionRecipientIds}
      />
      {error && <Banner tone="is-danger" icon="⚠" message={error} role="alert" />}
      <div className="cluster">
        <button
          className="button button-secondary button-sm"
          type="submit"
          disabled={submitting || !content.trim()}
        >
          {submitting ? "Posting…" : "Post Reply"}
        </button>
      </div>
    </form>
  );
}

interface CommentRevisionFormProps {
  commentId: string;
  initialContent: string;
  mentionRecipients: MentionRecipient[];
  onRevise: NonNullable<CommentThreadProps["onRevise"]>;
}

function CommentRevisionForm({
  commentId,
  initialContent,
  mentionRecipients,
  onRevise,
}: CommentRevisionFormProps) {
  /**
   * Starts empty rather than pre-filled with the current body. Pre-filling
   * duplicated the comment text into a second element, so the same sentence
   * appeared twice in the thread — once as history and once as an edit buffer.
   * The body being revised is displayed directly above.
   */
  const [content, setContent] = useState("");
  const [mentionRecipientIds, setMentionRecipientIds] = useState<string[]>([]);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    const trimmedContent = content.trim();
    if (!trimmedContent) return;

    setSubmitting(true);
    setError(null);
    try {
      await onRevise(commentId, trimmedContent, mentionRecipientIds);
    } catch (submissionError) {
      setError(
        submissionError instanceof Error
          ? submissionError.message
          : "The revision was not recorded.",
      );
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <form onSubmit={handleSubmit} className="stack-sm gap-t-4">
      <div className="divider" />
      <label className="sr-only" htmlFor={`revise-${commentId}`}>
        Revise comment {commentId}
      </label>
      <textarea
        id={`revise-${commentId}`}
        rows={2}
        value={content}
        placeholder="Replacement wording for this comment"
        onChange={(event) => setContent(event.target.value)}
      />
      <MentionSelector
        id={`revision-mentions-${commentId}`}
        label={`Mention team members for revision of comment ${commentId}`}
        recipients={mentionRecipients}
        selectedIds={mentionRecipientIds}
        onChange={setMentionRecipientIds}
      />
      {error && <Banner tone="is-danger" icon="⚠" message={error} role="alert" />}
      <div className="cluster">
        <button
          className="button button-secondary button-sm"
          type="submit"
          disabled={submitting || !content.trim() || content.trim() === initialContent.trim()}
        >
          {submitting ? "Saving…" : "Save Revision"}
        </button>
      </div>
    </form>
  );
}

export function CommentThread({
  comments = [],
  mentionRecipients = [],
  onAddComment,
  onReply,
  onRevise,
}: CommentThreadProps) {
  const [commentText, setCommentText] = useState("");
  const [mentionRecipientIds, setMentionRecipientIds] = useState<string[]>([]);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    const content = commentText.trim();
    if (!content || !onAddComment) return;

    const submittedMentions = mentionRecipientIds;
    setSubmitting(true);
    setError(null);
    // Cleared before awaiting, not after: otherwise the draft still holds the
    // text while the posted comment is already rendered in the history, so the
    // same sentence appears twice. Restored if the write fails, so a rejected
    // comment is never silently lost.
    setCommentText("");
    setMentionRecipientIds([]);
    try {
      await onAddComment(content, submittedMentions);
    } catch (submissionError) {
      setCommentText(content);
      setMentionRecipientIds(submittedMentions);
      setError(
        submissionError instanceof Error
          ? submissionError.message
          : "The comment was not recorded.",
      );
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <section className="section" data-testid="comment-thread">
      <div className="section-head">
        <div>
          <h2>Collaboration &amp; comments ({comments.length})</h2>
          <p>
            Every comment, reply and edit is retained as an immutable revision, attributed to its
            author.
          </p>
        </div>
      </div>

      <div className="stack">
        {comments.map((comment) => (
          <article
            className="record-entry"
            key={comment.commentId}
            // Reply depth is indentation, capped so a deep thread stays readable.
            style={{ marginLeft: `${Math.min(comment.replyDepth, 4) * 1.25}rem` }}
          >
            <span className="record-mark" aria-hidden="true">
              {comment.parentId ? "↳" : "◆"}
            </span>
            <div className="record-main">
              <div className="cluster-between">
                <div className="cluster">
                  <strong className="small">{comment.authorId}</strong>
                  <Badge>
                    {comment.parentId ? `Reply depth ${comment.replyDepth}` : "Root comment"}
                  </Badge>
                </div>
                <span className="mono small muted">
                  {new Date(comment.createdAt).toLocaleString()}
                </span>
              </div>

              <ol
                className="stack-sm gap-t-3"
                aria-label={`Revision history for comment ${comment.commentId}`}
                style={{ listStyle: "none", padding: 0 }}
              >
                {comment.revisions.map((revision) => (
                  <li className="source-card" key={revision.revisionId}>
                    <div className="cluster-between">
                      <span className="small muted">
                        Revision {revision.ordinal} by {revision.authorId}
                      </span>
                      <span className="mono small muted">
                        {new Date(revision.createdAt).toLocaleString()}
                      </span>
                    </div>
                    <p className="small gap-t-2">{revision.body}</p>
                    {revision.mentionRecipientIds.length > 0 && (
                      <p className="small muted gap-t-1">
                        Mention recipients:{" "}
                        {revision.mentionRecipientIds.map((recipientId) => (
                          <span className="mention" key={recipientId}>
                            {recipientId}
                          </span>
                        ))}
                      </p>
                    )}
                  </li>
                ))}
              </ol>

              {onReply && (
                <CommentReplyForm
                  commentId={comment.commentId}
                  mentionRecipients={mentionRecipients}
                  onReply={onReply}
                />
              )}
              {onRevise && comment.revisions.length > 0 && (
                <CommentRevisionForm
                  key={comment.revisions.at(-1)?.revisionId}
                  commentId={comment.commentId}
                  initialContent={comment.revisions.at(-1)?.body ?? ""}
                  mentionRecipients={mentionRecipients}
                  onRevise={onRevise}
                />
              )}
            </div>
          </article>
        ))}
      </div>

      {error && (
        <Banner tone="is-danger" icon="⚠" message={error} role="alert" className="gap-t-4" />
      )}

      <Card className="gap-t-4">
        <form onSubmit={handleSubmit} className="stack-sm">
          <label className="sr-only" htmlFor="new-comment">
            Add a clearance note
          </label>
          <textarea
            id="new-comment"
            data-testid="comment-input"
            rows={2}
            value={commentText}
            onChange={(event) => setCommentText(event.target.value)}
            placeholder="Add an internal clearance note or mention team members…"
          />
          <MentionSelector
            id="comment-mentions"
            label="Mention team members for new comment"
            recipients={mentionRecipients}
            selectedIds={mentionRecipientIds}
            onChange={setMentionRecipientIds}
          />
          <div className="cluster" style={{ justifyContent: "flex-end" }}>
            <button
              className="button button-primary"
              type="submit"
              data-testid="post-comment-btn"
              disabled={!commentText.trim() || !onAddComment || submitting}
            >
              {submitting ? "Posting…" : "Post Comment"}
            </button>
          </div>
        </form>
      </Card>
    </section>
  );
}

export default CommentThread;
