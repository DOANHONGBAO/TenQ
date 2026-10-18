import '@testing-library/jest-dom/vitest'
import { cleanup } from '@testing-library/react'
import { afterEach } from 'vitest'

// jsdom has no canvas: the decorative confetti simply draws nothing.
HTMLCanvasElement.prototype.getContext = () => null

afterEach(() => {
  cleanup()
  sessionStorage.clear()
  localStorage.clear()
})
