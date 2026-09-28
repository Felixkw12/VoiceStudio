import { useNavigate } from '@tanstack/react-router';
import { DownloadIcon, FingerprintIcon, PencilIcon, WandSparklesIcon } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { useState } from 'react';
import { toast } from 'sonner';
import { WorkspaceHeader } from '@/components/app-shell/workspace-header';
import { Button } from '@/components/ui/button';
import { WorkspacePane } from '@/components/workspace-pane';
import { useProfiles } from '@/hooks/use-profiles';
import { setWorkspace, useWorkspace } from '@/lib/store/workspace';
import { SavedVoices } from './voices-sidebar';
import { EditProfile } from './edit-profile';
import { runRendererTask } from '@/lib/global-error-recovery';
import { saveLocalFile } from '@/lib/local-export';
import { profilePromptsMarkdown } from './profile-prompts';

export function SavedVoicesPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { editingProfileId } = useWorkspace();
  const profiles = useProfiles();
  const [exporting, setExporting] = useState(false);
  const editing = profiles.data?.find((profile) => profile.id === editingProfileId);
  const closeEditor = () => setWorkspace({ editingProfileId: null });
  const exportPrompts = async () => {
    if (exporting || !profiles.data?.length) return;
    setExporting(true);
    try {
      const markdown = profilePromptsMarkdown(profiles.data, t);
      const result = await saveLocalFile(
        new Blob([markdown], { type: 'text/markdown;charset=utf-8' }),
        'voicestudio-voice-prompts.md',
      );
      if (!result.canceled) toast.success(t('clone.prompts_exported'));
    } catch {
      toast.error(t('clone.prompts_export_failed'));
    } finally {
      setExporting(false);
    }
  };
  return (
    <div className="flex h-full min-h-0 flex-col">
      <WorkspaceHeader>
        <h1 className="text-sm font-medium">{t('clone.saved_profiles')}</h1>
        <div className="flex items-center gap-1">
          <Button
            size="sm"
            variant="ghost"
            title={t('clone.export_prompts')}
            aria-label={t('clone.export_prompts')}
            disabled={!profiles.data?.length || exporting}
            onClick={() => void exportPrompts()}
          >
            <DownloadIcon />
            <span className="hidden sm:inline">{t('clone.export_prompts')}</span>
          </Button>
          <Button
            size="sm"
            variant="ghost"
            title={t('clone.title')}
            onClick={() => runRendererTask('Open voice cloning', () => navigate({ to: '/clone' }))}
          >
            <FingerprintIcon />
            <span className="hidden sm:inline">{t('clone.title')}</span>
          </Button>
          <Button
            size="sm"
            variant="ghost"
            title={t('designWorkspace.title')}
            onClick={() => runRendererTask('Open voice design', () => navigate({ to: '/design' }))}
          >
            <WandSparklesIcon />
            <span className="hidden sm:inline">{t('designWorkspace.title')}</span>
          </Button>
        </div>
      </WorkspaceHeader>
      <div className="flex min-h-0 flex-1">
        <div className="@container/library min-h-0 min-w-0 flex-1 overflow-y-auto p-4">
          <SavedVoices library onSelected={closeEditor} />
        </div>
        {editing && (
          <WorkspacePane
            layout="editor"
            title={t('paneActions.edit')}
            icon={PencilIcon}
            onClose={closeEditor}
          >
            <EditProfile key={editing.id} profile={editing} onDone={closeEditor} />
          </WorkspacePane>
        )}
      </div>
    </div>
  );
}
