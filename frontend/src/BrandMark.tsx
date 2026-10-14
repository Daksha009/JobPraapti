/** A rising arrow drawn into a J: finding your way to an opportunity. */
export function BrandMark({ size = 26 }: { size?: number }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 32 32"
      fill="none"
      aria-hidden="true"
    >
      <path
        d="M24 8v12a8 8 0 0 1-16 0v-2M15 8h9v9M24 8l-9 9"
        stroke="currentColor"
        strokeWidth="2.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <circle cx="8" cy="9" r="1.6" fill="currentColor" />
    </svg>
  );
}
