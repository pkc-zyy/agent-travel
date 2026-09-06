import ReactMarkdown from "react-markdown";

export default function Markdown({ content }: { content: string }) {
  return (
    <div className="md-body">
      <ReactMarkdown>{content}</ReactMarkdown>
    </div>
  );
}
