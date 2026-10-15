/**
 * REDLINE Animation Utilities powered by Anime.js v4
 * Safe for React 19, Next.js Turbopack SSR, and prefers-reduced-motion
 */

import { animate, createTimeline, stagger, type JSAnimation, type Timeline } from 'animejs';

/**
 * Checks if the user operating system or browser requests reduced motion
 */
export function prefersReducedMotion(): boolean {
  if (typeof window === 'undefined' || !window.matchMedia) {
    return false;
  }
  return window.matchMedia('(prefers-reduced-motion: reduce)').matches;
}

/**
 * Animate entrance for dashboard sections (staggered fade and subtle rise)
 * Skips gracefully if prefers-reduced-motion is enabled
 */
export function animateEntrance(
  targets: HTMLElement[] | NodeListOf<HTMLElement> | string,
  onComplete?: () => void
): JSAnimation | null {
  if (prefersReducedMotion() || typeof window === 'undefined') {
    onComplete?.();
    return null;
  }

  try {
    return animate(targets, {
      opacity: [0, 1],
      translateY: [14, 0],
      duration: 380,
      ease: 'outCubic',
      delay: stagger(45),
      onComplete: () => {
        onComplete?.();
      }
    });
  } catch (err) {
    console.warn('[REDLINE Animation] Entrance animation skipped:', err);
    onComplete?.();
    return null;
  }
}

/**
 * Animate table row entrance once when real data arrives
 */
export function animateTableRows(
  targets: HTMLElement[] | NodeListOf<HTMLElement> | string
): JSAnimation | null {
  if (prefersReducedMotion() || typeof window === 'undefined') {
    return null;
  }

  try {
    return animate(targets, {
      opacity: [0, 1],
      translateX: [-8, 0],
      duration: 280,
      ease: 'outQuad',
      delay: stagger(30)
    });
  } catch (err) {
    console.warn('[REDLINE Animation] Row animation skipped:', err);
    return null;
  }
}

/**
 * Animate a numeric counter from a previous value to a new value
 * Operates purely on genuine numbers; never on fabricated hardware telemetry.
 */
export function animateNumber(
  element: HTMLElement | null,
  from: number,
  to: number,
  duration = 400
): JSAnimation | null {
  if (!element) return null;

  if (prefersReducedMotion() || from === to) {
    element.textContent = String(to);
    return null;
  }

  const obj = { val: from };
  try {
    return animate(obj, {
      val: to,
      duration,
      ease: 'outQuad',
      onRender: () => {
        if (element) {
          element.textContent = String(Math.round(obj.val));
        }
      },
      onComplete: () => {
        if (element) {
          element.textContent = String(to);
        }
      }
    });
  } catch {
    element.textContent = String(to);
    return null;
  }
}

/**
 * Animate subtle button feedback (e.g. submit press or post-submission success confirmation)
 */
export function animateButtonFeedback(
  target: HTMLElement | null,
  state: 'press' | 'success' | 'error'
): JSAnimation | null {
  if (!target || prefersReducedMotion()) return null;

  try {
    if (state === 'press') {
      return animate(target, {
        scale: [1, 0.96, 1],
        duration: 180,
        ease: 'outQuad'
      });
    } else if (state === 'success') {
      return animate(target, {
        scale: [1, 1.03, 1],
        duration: 300,
        ease: 'outBack'
      });
    } else if (state === 'error') {
      return animate(target, {
        translateX: [-4, 4, -3, 3, 0],
        duration: 250,
        ease: 'linear'
      });
    }
  } catch {
    return null;
  }
  return null;
}

export { animate, createTimeline, stagger };
