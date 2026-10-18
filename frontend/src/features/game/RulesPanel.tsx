export function RulesPanel({ defaultOpen }: { defaultOpen: boolean }) {
  return (
    <details className="card rules" open={defaultOpen}>
      <summary>How to play</summary>
      <ul>
        <li>There is one secret English word per day, the same for everyone.</li>
        <li>Ask up to 10 English yes/no questions, like “Is it an animal?”.</li>
        <li>
          Ask about <b>one</b> property at a time (“Is it red?”, not “Is it red and big?”), and
          about the thing itself, not its spelling: questions about letters, length, or
          alphabetical order get a <b>PENALTY</b>.
        </li>
        <li>
          The AI judge answers <b>YES</b>, <b>NO</b>, <b>IRRELEVANT</b>, or <b>PENALTY</b> for
          questions that are not genuine yes/no questions. Every answer uses one question.
        </li>
        <li>
          Every 2 questions or guesses unlock a <b>hint</b>, from vague to obvious (4 in total).
        </li>
        <li>
          Think you know it? Type the word in the <b>guess box</b>. A guess also uses one of your
          10 tries.
        </li>
        <li>Fewer questions and a faster time rank higher. A new word starts at 00:00 UTC.</li>
      </ul>
    </details>
  )
}
