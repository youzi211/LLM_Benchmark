export function createSingleFlight<TArgs extends unknown[], TResult>(
  request: (...args: TArgs) => Promise<TResult>,
): (...args: TArgs) => Promise<TResult> {
  let inFlight: Promise<TResult> | null = null;

  return (...args: TArgs) => {
    if (inFlight) return inFlight;
    try {
      inFlight = request(...args).finally(() => {
        inFlight = null;
      });
      return inFlight;
    } catch (error) {
      return Promise.reject(error);
    }
  };
}
