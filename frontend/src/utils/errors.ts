




export function extractErrorMessage(err: unknown, fallback = "An unexpected error occurred."): string {
  if (!err) return fallback;

  if (typeof err === "string") return err;

  if (typeof err === "object") {
    
    if ("response" in err && err.response && typeof err.response === "object") {
      const responseData = (err.response as { data?: unknown }).data;
      if (responseData && typeof responseData === "object") {
        
        if ("detail" in responseData) {
          const detail = (responseData as { detail: unknown }).detail;
          if (typeof detail === "string") return detail;
          if (Array.isArray(detail)) {
            return detail
              .map((d: any) => {
                if (typeof d === "string") return d;
                if (d && typeof d === "object") {
                  const loc = Array.isArray(d.loc) ? d.loc.join(" -> ") : "";
                  const msg = d.msg || JSON.stringify(d);
                  return loc ? `${loc}: ${msg}` : msg;
                }
                return String(d);
              })
              .join("; ");
          }
          if (typeof detail === "object" && detail !== null) {
            return JSON.stringify(detail);
          }
          return String(detail);
        }

        
        if ("message" in responseData && typeof (responseData as { message?: unknown }).message === "string") {
          return (responseData as { message: string }).message;
        }
      }
    }

    
    if (err instanceof Error) {
      return err.message;
    }

    
    if ("message" in err && typeof (err as { message?: unknown }).message === "string") {
      return (err as { message: string }).message;
    }
  }

  try {
    return String(err);
  } catch {
    return fallback;
  }
}
