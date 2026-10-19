"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { applyJob, dismissJob, saveJob } from "@/lib/api/jobs";
import type {
  JobDetail,
  JobSummary,
  Page,
  UserJobState,
} from "@/lib/types/job";

function patchJobCaches(
  queryClient: ReturnType<typeof useQueryClient>,
  jobId: string,
  nextState: UserJobState,
) {
  queryClient.setQueriesData<Page<JobSummary>>({ queryKey: ["jobs"] }, (data) => {
    if (!data) return data;
    return {
      ...data,
      items: data.items.map((j) =>
        j.id === jobId ? { ...j, user_state: nextState } : j,
      ),
    };
  });
  queryClient.setQueryData<JobDetail>(["job", jobId], (prev) =>
    prev ? { ...prev, user_state: nextState } : prev,
  );
}

function makeStateMutation(stateLabel: UserJobState) {
  return function useStateMutation() {
    const queryClient = useQueryClient();
    const fn =
      stateLabel === "SAVED"
        ? saveJob
        : stateLabel === "APPLIED"
          ? applyJob
          : dismissJob;

    return useMutation({
      mutationFn: (jobId: string) => fn(jobId),
      onMutate: async (jobId: string) => {
        await queryClient.cancelQueries({ queryKey: ["jobs"] });
        await queryClient.cancelQueries({ queryKey: ["job", jobId] });
        const prevLists = queryClient.getQueriesData<Page<JobSummary>>({
          queryKey: ["jobs"],
        });
        const prevDetail = queryClient.getQueryData<JobDetail>(["job", jobId]);
        patchJobCaches(queryClient, jobId, stateLabel);
        return { prevLists, prevDetail, jobId };
      },
      onError: (_err, _jobId, ctx) => {
        if (!ctx) return;
        for (const [key, data] of ctx.prevLists) {
          queryClient.setQueryData(key, data);
        }
        if (ctx.prevDetail) {
          queryClient.setQueryData(["job", ctx.jobId], ctx.prevDetail);
        }
      },
      onSettled: (_data, _err, jobId) => {
        queryClient.invalidateQueries({ queryKey: ["jobs"] });
        queryClient.invalidateQueries({ queryKey: ["job", jobId] });
      },
    });
  };
}

export const useSaveJob = makeStateMutation("SAVED");
export const useApplyJob = makeStateMutation("APPLIED");
export const useDismissJob = makeStateMutation("DISMISSED");
