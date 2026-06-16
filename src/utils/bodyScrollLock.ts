type BodyScrollSnapshot = {
  bodyOverflow: string;
  bodyOverscroll: string;
  bodyPosition: string;
  bodyTop: string;
  bodyLeft: string;
  bodyRight: string;
  bodyWidth: string;
  htmlOverflow: string;
  htmlOverscroll: string;
};

let activeLocks = 0;
let snapshot: BodyScrollSnapshot | null = null;
let lockedScrollY = 0;

export const lockBodyScroll = () => {
  if (typeof document === 'undefined' || typeof window === 'undefined') {
    return () => {};
  }

  activeLocks += 1;
  if (activeLocks === 1) {
    const body = document.body;
    const html = document.documentElement;
    lockedScrollY = window.scrollY || html.scrollTop || 0;
    snapshot = {
      bodyOverflow: body.style.overflow,
      bodyOverscroll: body.style.overscrollBehavior,
      bodyPosition: body.style.position,
      bodyTop: body.style.top,
      bodyLeft: body.style.left,
      bodyRight: body.style.right,
      bodyWidth: body.style.width,
      htmlOverflow: html.style.overflow,
      htmlOverscroll: html.style.overscrollBehavior,
    };

    body.style.overflow = 'hidden';
    body.style.overscrollBehavior = 'none';
    body.style.position = 'fixed';
    body.style.top = `-${lockedScrollY}px`;
    body.style.left = '0';
    body.style.right = '0';
    body.style.width = '100%';
    html.style.overflow = 'hidden';
    html.style.overscrollBehavior = 'none';
  }

  let released = false;
  return () => {
    if (released) return;
    released = true;
    activeLocks = Math.max(0, activeLocks - 1);
    if (activeLocks > 0) return;

    const restoreScrollY = lockedScrollY;
    const previous = snapshot;
    snapshot = null;
    lockedScrollY = 0;

    if (previous) {
      const body = document.body;
      const html = document.documentElement;
      body.style.overflow = previous.bodyOverflow;
      body.style.overscrollBehavior = previous.bodyOverscroll;
      body.style.position = previous.bodyPosition;
      body.style.top = previous.bodyTop;
      body.style.left = previous.bodyLeft;
      body.style.right = previous.bodyRight;
      body.style.width = previous.bodyWidth;
      html.style.overflow = previous.htmlOverflow;
      html.style.overscrollBehavior = previous.htmlOverscroll;
      window.scrollTo(0, restoreScrollY);
    }
  };
};
