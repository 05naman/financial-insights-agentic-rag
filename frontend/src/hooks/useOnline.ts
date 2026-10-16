import { useEffect, useState } from 'react'

export const ONLINE_EVENT = 'fi:online'

/** Tracks connectivity; fires `fi:online` on reconnect so data hooks can refetch. */
export function useOnline() {
  const [online, setOnline] = useState(() => (typeof navigator === 'undefined' ? true : navigator.onLine))
  useEffect(() => {
    const up = () => {
      setOnline(true)
      window.dispatchEvent(new Event(ONLINE_EVENT))
    }
    const down = () => setOnline(false)
    window.addEventListener('online', up)
    window.addEventListener('offline', down)
    // some environments (and a few mobile browsers) don't fire the events reliably: poll the flag too
    const poll = setInterval(() => {
      setOnline((prev) => {
        if (navigator.onLine && !prev) window.dispatchEvent(new Event(ONLINE_EVENT))
        return navigator.onLine
      })
    }, 1500)
    return () => {
      clearInterval(poll)
      window.removeEventListener('online', up)
      window.removeEventListener('offline', down)
    }
  }, [])
  return online
}
