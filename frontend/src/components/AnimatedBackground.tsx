/**
 * Page backdrop. Deliberately flat: a solid surface reads as a working tool rather
 * than a showreel. (This used to be a drifting gradient mesh, a starfield and three
 * animated colour orbs.) The component name is kept so the existing layouts resolve.
 */
export const AnimatedBackground = () => (
  <div className="fixed inset-0 -z-10 bg-background" aria-hidden="true" />
);
