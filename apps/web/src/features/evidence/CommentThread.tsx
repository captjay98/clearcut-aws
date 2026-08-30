import React, { useState } from "react";

export interface CommentItem {
  id: string;
  authorName: string;
  content: string;
  createdAt: string;
  replies?: CommentItem[];
}

export interface CommentThreadProps {
  comments: CommentItem[];
  onAddComment: (content: string, parentId?: string) => void;
}

export function CommentThread({ comments, onAddComment }: CommentThreadProps) {
  const [newContent, setNewContent] = useState("");
  const [replyingTo, setReplyingTo] = useState<string | null>(null);
  const [replyContent, setReplyContent] = useState("");

  const handleCreateParent = (e: React.FormEvent) => {
    e.preventDefault();
    if (!newContent.trim()) return;
    onAddComment(newContent);
    setNewContent("");
  };

  const handleCreateReply = (e: React.FormEvent, parentId: string) => {
    e.preventDefault();
    if (!replyContent.trim()) return;
    onAddComment(replyContent, parentId);
    setReplyContent("");
    setReplyingTo(null);
  };

  return (
    <div className="space-y-6">
      <form onSubmit={handleCreateParent} className="space-y-2">
        <textarea
          rows={2}
          value={newContent}
          onChange={(e) => setNewContent(e.target.value)}
          placeholder="Add to discussion (use @name to mention)..."
          className="w-full p-2.5 text-xs border border-slate-300 dark:border-slate-700 rounded-md bg-white dark:bg-slate-800"
        />
        <div className="flex justify-end">
          <button
            type="submit"
            className="px-3 py-1.5 bg-blue-600 hover:bg-blue-700 text-white rounded text-xs font-medium"
          >
            Post Comment
          </button>
        </div>
      </form>

      <div className="space-y-4 divide-y divide-slate-100 dark:divide-slate-800">
        {comments.map((c) => (
          <div key={c.id} className="pt-4 first:pt-0 space-y-3">
            <div>
              <div className="flex items-center justify-between text-xs text-slate-500 mb-1">
                <span className="font-semibold text-slate-900 dark:text-white">{c.authorName}</span>
                <span>{c.createdAt}</span>
              </div>
              <p className="text-xs text-slate-700 dark:text-slate-300">{c.content}</p>
              <button
                type="button"
                onClick={() => setReplyingTo(replyingTo === c.id ? null : c.id)}
                className="mt-1 text-[11px] text-blue-600 dark:text-blue-400 hover:underline"
              >
                Reply
              </button>
            </div>

            {/* 1-Level Replies */}
            {c.replies && c.replies.length > 0 && (
              <div className="ml-6 pl-3 border-l-2 border-slate-200 dark:border-slate-700 space-y-2">
                {c.replies.map((r) => (
                  <div key={r.id}>
                    <div className="flex items-center justify-between text-[11px] text-slate-500">
                      <span className="font-medium text-slate-800 dark:text-slate-200">{r.authorName}</span>
                      <span>{r.createdAt}</span>
                    </div>
                    <p className="text-xs text-slate-700 dark:text-slate-300">{r.content}</p>
                  </div>
                ))}
              </div>
            )}

            {replyingTo === c.id && (
              <form onSubmit={(e) => handleCreateReply(e, c.id)} className="ml-6 space-y-2 pt-2">
                <input
                  type="text"
                  value={replyContent}
                  onChange={(e) => setReplyContent(e.target.value)}
                  placeholder="Write a reply..."
                  className="w-full p-2 text-xs border border-slate-300 dark:border-slate-700 rounded bg-white dark:bg-slate-800"
                />
                <div className="flex justify-end space-x-2">
                  <button
                    type="button"
                    onClick={() => setReplyingTo(null)}
                    className="px-2 py-1 text-xs border rounded"
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    className="px-2.5 py-1 bg-blue-600 text-white rounded text-xs font-medium"
                  >
                    Reply
                  </button>
                </div>
              </form>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
