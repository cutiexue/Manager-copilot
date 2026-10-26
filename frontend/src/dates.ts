// Calendar dates from the backend ("2026-04-01") formatted for reading. They are read as UTC
// midnight so the weekday never shifts with the viewer's time zone.
const asDate = (iso: string) => new Date(`${iso}T00:00:00Z`);

/** "Wednesday 1 April 2026" */
export const longDate = (iso: string) =>
  asDate(iso).toLocaleDateString('en-GB', { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric', timeZone: 'UTC' });

/** "Tue 31 Mar" */
export const shortDate = (iso: string) =>
  asDate(iso).toLocaleDateString('en-GB', { weekday: 'short', day: 'numeric', month: 'short', timeZone: 'UTC' });
