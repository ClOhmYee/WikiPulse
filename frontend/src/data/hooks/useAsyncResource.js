import { useEffect, useState } from "react";

export function useAsyncResource(load, key) {
  const [attempt, setAttempt] = useState(0);
  const [state, setState] = useState({
    key: null,
    attempt: -1,
    data: null,
    error: null,
    loading: true,
  });
  useEffect(() => {
    const controller = new AbortController();
    let current = true;
    Promise.resolve()
      .then(() => load(controller.signal))
      .then(
        (data) => {
          if (current)
            setState({ key, attempt, data, error: null, loading: false });
        },
        (error) => {
          if (current)
            setState({ key, attempt, data: null, error, loading: false });
        },
      );
    return () => {
      current = false;
      controller.abort();
    };
  }, [load, key, attempt]);
  const pending = state.key !== key || state.attempt !== attempt;
  return {
    data: pending ? null : state.data,
    previousData: state.data,
    error: pending ? null : state.error,
    loading: pending || state.loading,
    reload: () => setAttempt((value) => value + 1),
  };
}
