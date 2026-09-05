import type { ItemDetailComment, Membership } from "@clearcut/contracts";
import React, { useState } from "react";

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

function MentionSelector({
  id,
  label,
  recipients,
  selectedIds,
  onChange,
}: MentionSelectorProps) {
  return (
    <div className="space-y-1">
      <label htmlFor={id} className="block text-[10px] text-slate-400">
        {label}
      </label>
      <select
        id={id}
        multiple
        value={selectedIds}
        onChange={(event) =>
          onChange(
            Array.from(event.currentTarget.selectedOptions, (option) => option.value),
          )
        }
        className="w-full rounded border border-slate-700 bg-slate-800 p-2 text-xs text-white"
      >
        {recipients.map((recipient) => (
          <option key={recipient.userId} value={recipient.userId}>
            {recipient.email ?? recipient.userId} ({recipient.role})
          </option>
        ))}
      </select>
      <p className="text-[10px] text-slate-500">
        Select only active members authorized for this project.
      </p>
    </div>
  );
}

interface CommentReplyFormProps {
  commentId: string;
  mentionRecipients: MentionRecipient[];
  onReply: NonNullable<CommentThreadProps["onReply"]>;
}

function CommentReplyForm({
  commentId,
  mentionRecipients,
  onReply,
}: CommentReplyFormProps) {
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
      await onReply(commentId, trimmedContent, mentionRecipientIds);
      setContent("");
      setMentionRecipientIds([]);
    } catch (submissionError) {
      setError(
        submissionError instanceof Error ? submissionError.message : "The reply was not recorded.",
      );
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-2 border-t border-slate-800 pt-2">
      <label htmlFor={`reply-${commentId}`} className="sr-only">
        Reply to comment {commentId}
      </label>
      <textarea
        id={`reply-${commentId}`}
        rows={2}
        value={content}
        onChange={(event) => setContent(event.target.value)}
        className="w-full rounded border border-slate-700 bg-slate-800 p-2 text-xs text-white"
      />
      <MentionSelector
        id={`reply-mentions-${commentId}`}
        label={`Mention team members for reply to comment ${commentId}`}
        recipients={mentionRecipients}
        selectedIds={mentionRecipientIds}
        onChange={setMentionRecipientIds}
      />
      {error ? <p role="alert" className="text-xs text-rose-300">{error}</p> : null}
      <button
        type="submit"
        disabled={submitting || !content.trim()}
        className="rounded bg-slate-700 px-3 py-1 text-xs font-semibold text-white disabled:opacity-50"
      >
        {submitting ? "Posting…" : "Post Reply"}
      </button>
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
  const [content, setContent] = useState(initialContent);
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
    <form onSubmit={handleSubmit} className="space-y-2 border-t border-slate-800 pt-2">
      <label htmlFor={`revise-${commentId}`} className="sr-only">
        Revise comment {commentId}
      </label>
      <textarea
        id={`revise-${commentId}`}
        rows={2}
        value={content}
        onChange={(event) => setContent(event.target.value)}
        className="w-full rounded border border-slate-700 bg-slate-800 p-2 text-xs text-white"
      />
      <MentionSelector
        id={`revision-mentions-${commentId}`}
        label={`Mention team members for revision of comment ${commentId}`}
        recipients={mentionRecipients}
        selectedIds={mentionRecipientIds}
        onChange={setMentionRecipientIds}
      />
      {error ? <p role="alert" className="text-xs text-rose-300">{error}</p> : null}
      <button
        type="submit"
        disabled={submitting || !content.trim() || content.trim() === initialContent.trim()}
        className="rounded bg-slate-700 px-3 py-1 text-xs font-semibold text-white disabled:opacity-50"
      >
        {submitting ? "Saving…" : "Save Revision"}
      </button>
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

    setSubmitting(true);
    setError(null);
    try {
      await onAddComment(content, mentionRecipientIds);
      setCommentText("");
      setMentionRecipientIds([]);
    } catch (submissionError) {
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
    <div data-testid="comment-thread" className="space-y-4 font-sans">
      <div className="flex items-center justify-between pb-2 border-b border-slate-800 text-xs font-bold text-slate-300 uppercase tracking-wider">
        <span>Collaboration & Comments ({comments.length})</span>
        <span className="text-[10px] text-slate-500 font-normal lowercase">audit traceable</span>
      </div>

      <div className="space-y-3">
        {comments.map((comment) => (
          <article
            key={comment.commentId}
            className="p-3.5 bg-slate-900 border border-slate-800 rounded-lg space-y-2 shadow-sm"
            style={{ marginLeft: `${Math.min(comment.replyDepth, 4) * 1.25}rem` }}
          >
            <div className="flex items-center justify-between text-xs">
              <div className="flex items-center space-x-2">
                <span className="font-bold text-slate-200">{comment.authorId}</span>
                <span className="text-[10px] px-1.5 py-0.5 bg-slate-800 text-slate-400 rounded">
                  {comment.parentId ? `Reply depth ${comment.replyDepth}` : "Root comment"}
                </span>
              </div>
              <span className="text-[10px] text-slate-500 font-mono">
                {new Date(comment.createdAt).toLocaleString()}
              </span>
            </div>
            <ol aria-label={`Revision history for comment ${comment.commentId}`} className="space-y-2">
              {comment.revisions.map((revision) => (
                <li key={revision.revisionId} className="rounded bg-slate-950/60 p-2">
                  <div className="flex justify-between gap-2 text-[10px] text-slate-500">
                    <span>
                      Revision {revision.ordinal} by {revision.authorId}
                    </span>
                    <span>{new Date(revision.createdAt).toLocaleString()}</span>
                  </div>
                  <p className="mt-1 text-xs text-slate-300 leading-relaxed">{revision.body}</p>
                  {revision.mentionRecipientIds.length > 0 ? (
                    <p className="mt-1 text-[10px] text-slate-500">
                      Mention recipients: {revision.mentionRecipientIds.join(", ")}
                    </p>
                  ) : null}
                </li>
              ))}
            </ol>
            {onReply ? (
              <CommentReplyForm
                commentId={comment.commentId}
                mentionRecipients={mentionRecipients}
                onReply={onReply}
              />
            ) : null}
            {onRevise && comment.revisions.length > 0 ? (
              <CommentRevisionForm
                key={comment.revisions.at(-1)?.revisionId}
                commentId={comment.commentId}
                initialContent={comment.revisions.at(-1)?.body ?? ""}
                mentionRecipients={mentionRecipients}
                onRevise={onRevise}
              />
            ) : null}
          </article>
        ))}
      </div>

      {error && (
        <div role="alert" className="rounded border border-rose-900 bg-rose-950/40 p-2 text-xs text-rose-300">
          {error}
        </div>
      )}

      <form onSubmit={handleSubmit} className="space-y-2">
        <textarea
          data-testid="comment-input"
          rows={2}
          value={commentText}
          onChange={(event) => setCommentText(event.target.value)}
          placeholder="Add an internal clearance note or mention team members..."
          className="w-full p-2.5 text-xs bg-slate-800 border border-slate-700 rounded-md text-white placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-amber-500"
        />
        <MentionSelector
          id="comment-mentions"
          label="Mention team members for new comment"
          recipients={mentionRecipients}
          selectedIds={mentionRecipientIds}
          onChange={setMentionRecipientIds}
        />
        <div className="flex justify-end">
          <button
            type="submit"
            data-testid="post-comment-btn"
            disabled={!commentText.trim() || !onAddComment || submitting}
            className="px-3.5 py-1.5 bg-amber-600 hover:bg-amber-700 disabled:opacity-50 text-white font-bold text-xs rounded-md shadow focus:outline-none focus:ring-2 focus:ring-amber-500"
          >
            {submitting ? "Posting…" : "Post Comment"}
          </button>
        </div>
      </form>
    </div>
  );
}

export default CommentThread;
