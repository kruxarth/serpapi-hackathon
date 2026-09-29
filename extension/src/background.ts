// Service worker: the only place (besides the side panel) that talks to the local backend.
import { lookupPlace, tabKey, type TabPlace } from './shared'

chrome.runtime.onInstalled.addListener(() => {
  // Fallback: the toolbar icon always opens the side panel, even if a relayed open is refused.
  chrome.sidePanel.setPanelBehavior({ openPanelOnActionClick: true }).catch(() => {})
})
chrome.runtime.onStartup.addListener(() => {
  chrome.sidePanel.setPanelBehavior({ openPanelOnActionClick: true }).catch(() => {})
})

chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  const tabId = sender.tab?.id
  if (msg?.type === 'placeChanged' && tabId !== undefined) {
    ;(async () => {
      const lookup = await lookupPlace(String(msg.url))
      const place: TabPlace = { url: String(msg.url), dataId: lookup.state === 'none' ? lookup.dataId ?? null : null, lookup }
      await chrome.storage.session.set({ [tabKey(tabId)]: place })
      sendResponse({ lookup })
    })()
    return true
  }
  if (msg?.type === 'openPanel' && tabId !== undefined) {
    // Must run synchronously in the message handler to keep the user gesture.
    chrome.sidePanel
      .open({ tabId })
      .then(() => sendResponse({ ok: true }))
      .catch(() => sendResponse({ ok: false }))
    return true
  }
  return false
})

chrome.tabs.onRemoved.addListener((tabId) => {
  chrome.storage.session.remove(tabKey(tabId)).catch(() => {})
})
