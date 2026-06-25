import { useState } from 'react';
import { motion } from 'framer-motion';
import {
  Settings as SettingsIcon,
  User,
  Bell,
  FileText,
  Palette,
  ChevronRight,
  Save,
} from 'lucide-react';
import { AppLayout } from '@/components/AppLayout';
import { cn } from '@/lib/utils';
import { Switch } from '@/components/ui/switch';
import { toast } from 'sonner';

type SettingsSection = 'profile' | 'notifications' | 'analysis' | 'exports' | 'appearance';

const sections = [
  { id: 'profile' as const, label: 'Profile', icon: User },
  { id: 'notifications' as const, label: 'Notifications', icon: Bell },
  { id: 'analysis' as const, label: 'Analysis', icon: SettingsIcon },
  { id: 'exports' as const, label: 'Exports', icon: FileText },
  { id: 'appearance' as const, label: 'Appearance', icon: Palette },
];

const DEFAULTS = {
  // Profile (blank by default — no fabricated identity, no auth backend)
  displayName: '',
  email: '',
  organization: '',
  // Notifications (local preferences)
  integrityGapAlerts: true,
  newClaimAlerts: true,
  weeklyDigest: false,
  // Analysis thresholds
  confidenceThreshold: 70,
  autoReviewThreshold: 50,
  includeHistoricalData: true,
  // Exports
  defaultFormat: 'json',
  includeMethodology: true,
  // Appearance
  compactMode: false,
  animationsEnabled: true,
};

const Settings = () => {
  const [activeSection, setActiveSection] = useState<SettingsSection>('profile');
  const [isSaving, setIsSaving] = useState(false);

  const [settings, setSettings] = useState(() => {
    try {
      const saved = typeof window !== 'undefined' ? localStorage.getItem('esgenuine_settings') : null;
      return saved ? { ...DEFAULTS, ...JSON.parse(saved) } : DEFAULTS;
    } catch {
      return DEFAULTS;
    }
  });

  const updateSetting = (key: string, value: any) => {
    setSettings(prev => ({ ...prev, [key]: value }));
  };

  const handleSave = async () => {
    setIsSaving(true);
    localStorage.setItem('esgenuine_settings', JSON.stringify(settings));
    await new Promise(resolve => setTimeout(resolve, 300));
    setIsSaving(false);
    toast.success('Settings saved locally');
  };

  const initials =
    settings.displayName.trim().split(/\s+/).filter(Boolean).map((p: string) => p[0]).slice(0, 2).join('').toUpperCase() || '–';

  const renderSection = () => {
    switch (activeSection) {
      case 'profile':
        return (
          <div className="space-y-6">
            <div>
              <h3 className="text-lg font-medium text-foreground mb-1">Profile</h3>
              <p className="text-xs text-muted-foreground mb-4">
                Stored locally in your browser. There is no account/login backend.
              </p>
              <div className="space-y-4">
                <div className="flex items-center gap-4">
                  <div className="w-20 h-20 rounded-full bg-gradient-to-br from-primary to-primary/60 flex items-center justify-center text-2xl font-bold text-primary-foreground">
                    {initials}
                  </div>
                </div>
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <label className="text-sm text-muted-foreground block mb-1.5">Display Name</label>
                    <input
                      type="text"
                      placeholder="Your name"
                      value={settings.displayName}
                      onChange={(e) => updateSetting('displayName', e.target.value)}
                      className="w-full px-4 py-2.5 rounded-lg bg-muted/50 border border-border/50 text-foreground focus:outline-none focus:ring-2 focus:ring-primary/50"
                    />
                  </div>
                  <div>
                    <label className="text-sm text-muted-foreground block mb-1.5">Email</label>
                    <input
                      type="email"
                      placeholder="you@example.com"
                      value={settings.email}
                      onChange={(e) => updateSetting('email', e.target.value)}
                      className="w-full px-4 py-2.5 rounded-lg bg-muted/50 border border-border/50 text-foreground focus:outline-none focus:ring-2 focus:ring-primary/50"
                    />
                  </div>
                  <div className="col-span-2">
                    <label className="text-sm text-muted-foreground block mb-1.5">Organization</label>
                    <input
                      type="text"
                      placeholder="Organization (optional)"
                      value={settings.organization}
                      onChange={(e) => updateSetting('organization', e.target.value)}
                      className="w-full px-4 py-2.5 rounded-lg bg-muted/50 border border-border/50 text-foreground focus:outline-none focus:ring-2 focus:ring-primary/50"
                    />
                  </div>
                </div>
              </div>
            </div>
          </div>
        );

      case 'notifications':
        return (
          <div className="space-y-6">
            <div>
              <h3 className="text-lg font-medium text-foreground mb-1">Alert Preferences</h3>
              <p className="text-xs text-muted-foreground mb-4">In-app preferences (saved locally).</p>
              <div className="space-y-4">
                <SettingToggle
                  label="Integrity Gap Alerts"
                  description="Highlight claims flagged as integrity gaps"
                  checked={settings.integrityGapAlerts}
                  onChange={(v) => updateSetting('integrityGapAlerts', v)}
                />
                <SettingToggle
                  label="New Claim Notifications"
                  description="Surface newly added claims that need review"
                  checked={settings.newClaimAlerts}
                  onChange={(v) => updateSetting('newClaimAlerts', v)}
                />
                <SettingToggle
                  label="Weekly Digest"
                  description="Show a weekly portfolio integrity summary"
                  checked={settings.weeklyDigest}
                  onChange={(v) => updateSetting('weeklyDigest', v)}
                />
              </div>
            </div>
          </div>
        );

      case 'analysis':
        return (
          <div className="space-y-6">
            <div>
              <h3 className="text-lg font-medium text-foreground mb-4">Confidence Thresholds</h3>
              <div className="space-y-6">
                <div>
                  <div className="flex items-center justify-between mb-2">
                    <label className="text-sm text-foreground">Verification Confidence Threshold</label>
                    <span className="text-sm font-mono text-primary">{settings.confidenceThreshold}%</span>
                  </div>
                  <input
                    type="range" min="0" max="100"
                    value={settings.confidenceThreshold}
                    onChange={(e) => updateSetting('confidenceThreshold', parseInt(e.target.value))}
                    className="w-full h-2 rounded-full bg-muted appearance-none cursor-pointer [&::-webkit-slider-thumb]:appearance-none [&::-webkit-slider-thumb]:w-4 [&::-webkit-slider-thumb]:h-4 [&::-webkit-slider-thumb]:rounded-full [&::-webkit-slider-thumb]:bg-primary [&::-webkit-slider-thumb]:cursor-pointer"
                  />
                  <p className="text-xs text-muted-foreground mt-1">Claims above this groundability are marked verified</p>
                </div>
                <div>
                  <div className="flex items-center justify-between mb-2">
                    <label className="text-sm text-foreground">Auto-Review Threshold</label>
                    <span className="text-sm font-mono text-warning">{settings.autoReviewThreshold}%</span>
                  </div>
                  <input
                    type="range" min="0" max="100"
                    value={settings.autoReviewThreshold}
                    onChange={(e) => updateSetting('autoReviewThreshold', parseInt(e.target.value))}
                    className="w-full h-2 rounded-full bg-muted appearance-none cursor-pointer [&::-webkit-slider-thumb]:appearance-none [&::-webkit-slider-thumb]:w-4 [&::-webkit-slider-thumb]:h-4 [&::-webkit-slider-thumb]:rounded-full [&::-webkit-slider-thumb]:bg-warning [&::-webkit-slider-thumb]:cursor-pointer"
                  />
                  <p className="text-xs text-muted-foreground mt-1">Claims below this groundability are flagged for review</p>
                </div>
              </div>
            </div>
            <div className="border-t border-border/30 pt-6">
              <SettingToggle
                label="Include Historical Data"
                description="Use prior-year reports in cross-report comparisons"
                checked={settings.includeHistoricalData}
                onChange={(v) => updateSetting('includeHistoricalData', v)}
              />
            </div>
          </div>
        );

      case 'exports':
        return (
          <div className="space-y-6">
            <div>
              <h3 className="text-lg font-medium text-foreground mb-4">Export Preferences</h3>
              <div className="space-y-4">
                <div>
                  <label className="text-sm text-muted-foreground block mb-2">Default Export Format</label>
                  <div className="flex gap-2">
                    {['json', 'csv'].map(format => (
                      <button
                        key={format}
                        onClick={() => updateSetting('defaultFormat', format)}
                        className={cn(
                          'px-4 py-2 rounded-lg text-sm uppercase font-mono transition-all',
                          settings.defaultFormat === format
                            ? 'bg-primary text-primary-foreground'
                            : 'bg-muted/50 text-muted-foreground hover:text-foreground border border-border/50'
                        )}
                      >
                        {format}
                      </button>
                    ))}
                  </div>
                </div>
                <SettingToggle
                  label="Include Methodology"
                  description="Append the scoring methodology to exported reports"
                  checked={settings.includeMethodology}
                  onChange={(v) => updateSetting('includeMethodology', v)}
                />
              </div>
            </div>
          </div>
        );

      case 'appearance':
        return (
          <div className="space-y-6">
            <div>
              <h3 className="text-lg font-medium text-foreground mb-4">Theme</h3>
              <div className="p-4 rounded-lg border border-primary bg-primary/10 inline-block">
                <span className="text-sm font-medium text-foreground block">Dark</span>
                <span className="text-xs text-muted-foreground">The only theme currently available</span>
              </div>
            </div>
            <div className="border-t border-border/30 pt-6">
              <h3 className="text-lg font-medium text-foreground mb-4">Display Options</h3>
              <div className="space-y-4">
                <SettingToggle
                  label="Compact Mode"
                  description="Reduce spacing for more information density"
                  checked={settings.compactMode}
                  onChange={(v) => updateSetting('compactMode', v)}
                />
                <SettingToggle
                  label="Animations"
                  description="Enable smooth transitions and micro-interactions"
                  checked={settings.animationsEnabled}
                  onChange={(v) => updateSetting('animationsEnabled', v)}
                />
              </div>
            </div>
          </div>
        );

      default:
        return null;
    }
  };

  return (
    <AppLayout>
      <motion.header
        className="h-16 border-b border-border/30 glass-panel flex items-center justify-between px-6"
        initial={{ opacity: 0, y: -20 }}
        animate={{ opacity: 1, y: 0 }}
      >
        <div>
          <h1 className="text-lg font-semibold text-foreground">Settings</h1>
          <p className="text-xs text-muted-foreground">Local preferences for the ESGenuine dashboard</p>
        </div>
        <motion.button
          onClick={handleSave}
          disabled={isSaving}
          className="btn-neon flex items-center gap-2 text-sm disabled:opacity-50"
          whileHover={{ scale: 1.02 }}
          whileTap={{ scale: 0.98 }}
        >
          {isSaving ? (
            <div className="w-4 h-4 border-2 border-primary-foreground/30 border-t-primary-foreground rounded-full animate-spin" />
          ) : (
            <Save className="w-4 h-4" />
          )}
          Save Changes
        </motion.button>
      </motion.header>

      <div className="flex-1 flex overflow-hidden">
        <motion.nav
          className="w-64 border-r border-border/30 p-4 overflow-y-auto"
          initial={{ opacity: 0, x: -20 }}
          animate={{ opacity: 1, x: 0 }}
        >
          <div className="space-y-1">
            {sections.map((section, i) => (
              <motion.button
                key={section.id}
                onClick={() => setActiveSection(section.id)}
                className={cn(
                  'w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-left transition-all',
                  activeSection === section.id
                    ? 'bg-primary/15 text-primary'
                    : 'text-muted-foreground hover:text-foreground hover:bg-muted/30'
                )}
                initial={{ opacity: 0, x: -10 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ delay: i * 0.05 }}
              >
                <section.icon className="w-4 h-4" />
                <span className="text-sm">{section.label}</span>
                {activeSection === section.id && <ChevronRight className="w-4 h-4 ml-auto" />}
              </motion.button>
            ))}
          </div>
        </motion.nav>

        <motion.div
          className="flex-1 p-6 overflow-y-auto"
          key={activeSection}
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.2 }}
        >
          <div className="max-w-2xl">{renderSection()}</div>
        </motion.div>
      </div>
    </AppLayout>
  );
};

const SettingToggle = ({
  label,
  description,
  checked,
  onChange,
}: {
  label: string;
  description: string;
  checked: boolean;
  onChange: (v: boolean) => void;
}) => (
  <div className="flex items-start justify-between gap-4 p-3 rounded-lg hover:bg-muted/20 transition-colors">
    <div>
      <span className="text-sm font-medium text-foreground">{label}</span>
      <span className="block text-xs text-muted-foreground">{description}</span>
    </div>
    <Switch checked={checked} onCheckedChange={onChange} />
  </div>
);

export default Settings;
