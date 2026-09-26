import React from "react";

export function sanitizeAssistantText(value) {
  return String(value || "")
    .replace(/<br\s*\/?>(\s*)/gi, "\n")
    .replace(/\bENT-[A-Z0-9-]+\b/gi, "ce dossier")
    .replace(/(t[ée]l[ée]phone\s*[:\-]?\s*)[+\d().\s-]{7,}/gi, "$1coordonnée masquée")
    .replace(/(adresse\s*[:\-]?\s*)[^|\n]+/gi, "$1adresse masquée")
    .replace(/(?:matricule fiscal|identifiant fiscal|registre fiscal)\s*[:\-]?\s*[^|\n]+/gi, "information fiscale confidentielle")
    .replace(/score de correspondance/gi, "niveau de rapprochement");
}

function inlineContent(value) {
  const tokens = String(value).split(/(\*\*[^*]+\*\*|`[^`]+`)/g).filter(Boolean);
  return tokens.map((token, index) => {
    if (token.startsWith("**") && token.endsWith("**")) return <strong key={index}>{token.slice(2, -2)}</strong>;
    if (token.startsWith("`") && token.endsWith("`")) return <code key={index}>{token.slice(1, -1)}</code>;
    return <React.Fragment key={index}>{token}</React.Fragment>;
  });
}

function isTableSeparator(line) {
  return /^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)+\|?\s*$/.test(line);
}

function tableCells(line) {
  return line.trim().replace(/^\|/, "").replace(/\|$/, "").split("|").map((cell) => cell.trim());
}

export default function FormattedText({ text, className = "" }) {
  const lines = sanitizeAssistantText(text).split(/\r?\n/);
  const blocks = [];
  let index = 0;

  while (index < lines.length) {
    const line = lines[index].trim();
    if (!line) { index += 1; continue; }
    if (/^-{3,}$/.test(line)) { index += 1; continue; }

    if (line.includes("|") && index + 1 < lines.length && isTableSeparator(lines[index + 1])) {
      const headers = tableCells(line);
      const rows = [];
      index += 2;
      while (index < lines.length && lines[index].includes("|")) {
        rows.push(tableCells(lines[index]));
        index += 1;
      }
      blocks.push(
        <div className="rich-table-wrap" key={`table-${index}`}>
          <table className="rich-table"><thead><tr>{headers.map((cell, cellIndex) => <th key={cellIndex}>{inlineContent(cell)}</th>)}</tr></thead><tbody>{rows.map((row, rowIndex) => <tr key={rowIndex}>{headers.map((_, cellIndex) => <td key={cellIndex}>{inlineContent(row[cellIndex] || "")}</td>)}</tr>)}</tbody></table>
        </div>
      );
      continue;
    }

    const heading = line.match(/^#{1,4}\s+(.+)/);
    if (heading) {
      blocks.push(<h3 className="rich-heading" key={`heading-${index}`}>{inlineContent(heading[1])}</h3>);
      index += 1;
      continue;
    }

    if (/^(?:[-*]|\d+\.)\s+/.test(line)) {
      const ordered = /^\d+\./.test(line);
      const items = [];
      while (index < lines.length && new RegExp(ordered ? "^\\d+\\.\\s+" : "^[-*]\\s+").test(lines[index].trim())) {
        items.push(lines[index].trim().replace(ordered ? /^\d+\.\s+/ : /^[-*]\s+/, ""));
        index += 1;
      }
      const List = ordered ? "ol" : "ul";
      blocks.push(<List className="rich-list" key={`list-${index}`}>{items.map((item, itemIndex) => <li key={itemIndex}>{inlineContent(item)}</li>)}</List>);
      continue;
    }

    const paragraph = [line];
    index += 1;
    while (index < lines.length && lines[index].trim() && !/^#{1,4}\s+/.test(lines[index].trim()) && !/^(?:[-*]|\d+\.)\s+/.test(lines[index].trim()) && !(lines[index].includes("|") && index + 1 < lines.length && isTableSeparator(lines[index + 1]))) {
      paragraph.push(lines[index].trim());
      index += 1;
    }
    blocks.push(<p className="rich-paragraph" key={`paragraph-${index}`}>{inlineContent(paragraph.join(" "))}</p>);
  }

  return <div className={`rich-text ${className}`}>{blocks}</div>;
}
