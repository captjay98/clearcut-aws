import React, { useState } from "react";

export interface CommentItem {
  id: string;
  authorName: string;
  authorRole: string;
  content: string;
  createdAt: string;
  replies?: CommentItem[];
}

export interface CommentThreadProps {
  comments?: CommentItem[];
  onAddComment?: (content: string, parentId?: string) => void;
}

export function CommentThread({ comments = [], onAddComment }: CommentThreadProps) {
  const [commentText, setCommentText] = useState("");
  const [localComments, setLocalComments] = useState<CommentItem[]>(
    comments.length > 0
      ? comments
      : [
          {
            id: "c-1",
            authorName: "Sarah Chen",
            authorRole: "Legal Counsel",
            content: "Checked the mark against USPTO Class 09. No immediate trademark block identified.",
            createdAt: "2026-08-30T14:30:00Z",
          },
        ]
  );

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!commentText.trim()) return;

    const newComment: CommentItem = {
      id: `c-${Date.now()}`,
      authorName: "Jamie Park",
      authorRole: "Reviewer",
      content: commentText,
      createdAt: new Date().toISOString(),
    };

    setLocalComments((prev) => [...prev, newComment]);
    onAddComment?.(commentText);
    setCommentText("");
  };

  return (
    <div data-testid="comment-thread" className="space-y-4 font-sans">
      <div className="flex items-center justify-between pb-2 border-b border-slate-800 text-xs font-bold text-slate-300 uppercase tracking-wider">
        <span>Collaboration & Comments ({localComments.length})</span>
        <span className="text-[10px] text-slate-500 font-normal lowercase">audit traceable</span>
      </div>

      {/* Existing comments list */}
      <div className="space-y-3">
        {localComments.map((comment) => (
          <div key={comment.id} className="p-3.5 bg-slate-900 border border-slate-800 rounded-lg space-y-1.5 shadow-sm">
            <div className="flex items-center justify-between text-xs">
              <div className="flex items-center space-x-2">
                <span className="font-bold text-slate-200">{comment.authorName}</span>
                <span className="text-[10px] px-1.5 py-0.5 bg-slate-800 text-slate-400 rounded">
                  {comment.authorRole}
                </span>
              </div>
              <span className="text-[10px] text-slate-500 font-mono">
                {new Date(comment.createdAt).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
              </span>
            </div>
            <p className="text-xs text-slate-300 leading-relaxed">{comment.content}</p>
          </div>
        ))}
      </div>

      {/* Add comment form */}
      <form onSubmit={handleSubmit} className="space-y-2">
        <textarea
          data-testid="comment-input"
          rows={2}
          value={commentText}
          onChange={(e) => setCommentText(e.target.value)}
          placeholder="Add an internal clearance note or mention team members..."
          className="w-full p-2.5 text-xs bg-slate-800 border border-slate-700 rounded-md text-white placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-amber-500"
        />
        <div className="flex justify-end">
          <button
            type="submit"
            data-testid="post-comment-btn"
            disabled={!commentText.trim()}
            className="px-3.5 py-1.5 bg-amber-600 hover:bg-amber-700 disabled:opacity-50 text-white font-bold text-xs rounded-md shadow focus:outline-none focus:ring-2 focus:ring-amber-500"
          >
            Post Comment
          </button>
        </div>
      </form>
    </div>
  );
}

export default CommentThread;
