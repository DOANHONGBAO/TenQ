export function RulesPanel({ defaultOpen }: { defaultOpen: boolean }) {
  return (
    <details className="card rules" open={defaultOpen}>
      <summary>How to play</summary>
      <ul>
        <li>There is one secret English word per day, the same for everyone.</li>
        <li>Ask up to 10 English yes/no questions, like “Is it an animal?”.</li>
        <li>
          The AI judge answers <b>YES</b>, <b>NO</b>, <b>IRRELEVANT</b>, or <b>PENALTY</b> for
          questions that are not genuine yes/no questions. Every answer uses one question.
        </li>
        <li>Guess the word with a question such as “Is it a walrus?” to win.</li>
        <li>Fewer questions and a faster time rank higher. A new word starts at 00:00 UTC.</li>
      </ul>
    </details>
  )
}
