"use client";

import { useQueryClient } from "@tanstack/react-query";
import { useCallback } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { dismissJob } from "@/lib/api/jobs";
import { useApplyJob, useSaveJob } from "@/lib/hooks/use-job-mutations";
import type {
  JobDetail,
  JobSummary,
  Page,
  UserJobState,
} from "@/lib/types/job";

type Variant = "card" | "detail";

export function JobActions({
  jobId,
  state,
  variant,
}: {
  jobId: string;
  state: UserJobState | null | undefined;
  variant: Variant;
}) {
  const save = useSaveJob();
  const apply = useApplyJob();
  const queryClient = useQueryClient();

  const size = variant === "card" ? "xs" : "sm";
  const isPending = save.isPending || apply.isPending;

  const onDismissClick = useCallback(() => {
    const prevLists = queryClient.getQueriesData<Page<JobSummary>>({
      queryKey: ["jobs"],
    });
    const prevDetail = queryClient.getQueryData<JobDetail>(["job", jobId]);

    queryClient.cancelQueries({ queryKey: ["jobs"] });
    queryClient.cancelQueries({ queryKey: ["job", jobId] });

    queryClient.setQueriesData<Page<JobSummary>>(
      { queryKey: ["jobs"] },
      (data) => {
        if (!data) return data;
        return {
          ...data,
          items: data.items.filter((j) => j.id !== jobId),
          total: Math.max(0, data.total - 1),
        };
      },
    );
    queryClient.setQueryData<JobDetail>(["job", jobId], (prev) =>
      prev ? { ...prev, user_state: "DISMISSED" } : prev,
    );

    const restore = () => {
      for (const [key, data] of prevLists) {
        queryClient.setQueryData(key, data);
      }
      if (prevDetail) {
        queryClient.setQueryData(["job", jobId], prevDetail);
      }
    };

    toast("Job dismissed", {
      duration: 5000,
      action: {
        label: "Undo",
        onClick: restore,
      },
      onAutoClose: () => {
        dismissJob(jobId)
          .then(() => {
            queryClient.invalidateQueries({ queryKey: ["jobs"] });
            queryClient.invalidateQueries({ queryKey: ["job", jobId] });
          })
          .catch(() => {
            toast.error("Failed to dismiss");
            restore();
          });
      },
    });
  }, [queryClient, jobId]);

  const onSave = () => {
    save.mutate(jobId, {
      onError: () => toast.error("Failed to save"),
    });
  };
  const onApply = () => {
    apply.mutate(jobId, {
      onError: () => toast.error("Failed to mark as applied"),
    });
  };

  return (
    <div className="flex items-center gap-1.5">
      <Button
        size={size}
        variant={state === "SAVED" ? "default" : "outline"}
        disabled={isPending || state === "SAVED"}
        onClick={onSave}
      >
        {state === "SAVED" ? "Saved" : "Save"}
      </Button>
      <Button
        size={size}
        variant={state === "APPLIED" ? "default" : "outline"}
        disabled={isPending || state === "APPLIED"}
        onClick={onApply}
      >
        {state === "APPLIED" ? "Applied" : "Mark applied"}
      </Button>
      <Button
        size={size}
        variant="ghost"
        onClick={onDismissClick}
        aria-label="Dismiss"
        title="Dismiss"
      >
        Dismiss
      </Button>
    </div>
  );
}
