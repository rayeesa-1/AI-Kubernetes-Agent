import { useMutation } from "@tanstack/react-query";
import { api } from "@/services/api";
import type { InvestigationResponse } from "@/types/investigation";
export function useInvestigation() {
  return useMutation({
    mutationFn: async ({id, context}: {id: string; context: string}) => {
      const {data} = await api.post<InvestigationResponse>("/investigate", {context}, {
        timeout: 300000, headers: {"X-Investigation-ID": id},
      });
      if (!data || !data.investigation_id || !data.investigation) throw new Error("The backend returned an empty or unexpected result.");
      return data;
    },
    retry: false,
  });
}
