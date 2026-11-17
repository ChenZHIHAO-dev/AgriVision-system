export type Draft = { text: string; documents: string[]; images: string[] }
export function createDraftStore() {
  const drafts = new Map<string, Draft>()
  return {
    save(id: string, draft: Draft) {
      drafts.set(id, {
        text: draft.text,
        documents: [...draft.documents],
        images: [...draft.images],
      })
    },
    get(id: string): Draft {
      const draft = drafts.get(id)
      return draft
        ? { text: draft.text, documents: [...draft.documents], images: [...draft.images] }
        : { text: '', documents: [], images: [] }
    },
    clear() {
      drafts.clear()
    },
  }
}
