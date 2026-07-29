import ReactMarkdown from "react-markdown";

/** Renders markdown content with the app's shared `.markdown-content` styling. */
export function Markdown({ children }: { children: string }) {
  return (
    <div className="markdown-content">
      <ReactMarkdown>{children}</ReactMarkdown>
    </div>
  );
}
