// Small text helpers shared by the review cards and the walkthrough.

/** Where a normalized search-ad phrase ("packers and movers in hadapsar pune") sits in the original text. */
export function phraseSpan(text: string, phrase: string): [number, number] | null {
  const words = phrase.split(' ').filter(Boolean)
  if (!words.length) return null
  const re = new RegExp(words.map((w) => w.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')).join('[^a-z0-9]+'), 'i')
  const m = re.exec(text)
  return m ? [m.index, m.index + m[0].length] : null
}
