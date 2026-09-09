import React, { ReactNode } from "react";

export interface CardProps {
  title?: string;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
}

export function Card({ title, actions, children, className = "" }: CardProps) {
  return (
    <article className={`card ${className}`.trim()}>
      {(title || actions) && (
        <div className="card-head">
          <div>{title && <h2>{title}</h2>}</div>
          {actions}
        </div>
      )}
      {children}
    </article>
  );
}
