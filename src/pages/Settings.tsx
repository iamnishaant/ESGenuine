import { useState } from 'react';
import { motion } from 'framer-motion';
import { 
  Settings as SettingsIcon,
  User,
  Bell,
  Shield,
  Database,
  Satellite,
  FileText,
  Palette,
  Key,
  Globe2,
  ChevronRight,
  Check,
  AlertCircle,
  Mail,
  Smartphone,
  Save
} from 'lucide-react';
import { AppLayout } from '@/components/AppLayout';
import { cn } from '@/lib/utils';
import { Switch } from '@/components/ui/switch';
import { toast } from 'sonner';

type SettingsSection = 'profile' | 'notifications' | 'analysis' | 'data-sources' | 'exports' | 'security' | 'appearance' | 'api';

const sections = [
  { id: 'profile' as const, label: 'Profile & Account', icon: User },
  { id: 'notifications' as const, label: 'Notifications', icon: Bell },
  { id: 'analysis' as const, label: 'Analysis Settings', icon: SettingsIcon },
  { id: 'data-sources' as const, label: 'Data Sources', icon: Satellite },
  { id: 'exports' as const, label: 'Reports & Exports', icon: FileText },
  { id: 'security' as const, label: 'Security & Privacy', icon: Shield },
  { id: 'appearance' as const, label: 'Appearance', icon: Palette },
  { id: 'api' as const, label: 'API & Integrations', icon: Key },
];

const Settings = () => {
  const [activeSection, setActiveSection] = useState<SettingsSection>('profile');
  const [isSaving, setIsSaving] = useState(false);

  // Settings state
  const [settings, setSettings] = useState({
    // Profile
    displayName: 'Dr. Sarah Chen',
    email: 'sarah.chen@pharos-integrity.com',
    role: 'Senior ESG Analyst',
    organization: 'Global Sustainability Partners',
    
    // Notifications
    emailAlerts: true,
    integrityGapAlerts: true,
    newClaimAlerts: true,
    weeklyDigest: true,
    pushNotifications: false,
    slackIntegration: true,
    
    // Analysis
    confidenceThreshold: 70,
    autoReviewThreshold: 50,
    includeHistoricalData: true,
    multiTemporalAnalysis: true,
    sarDataEnabled: true,
    ndviCalculation: true,
    
    // Data Sources
    sentinel2: true,
    sentinel1Sar: true,
    landsat8: false,
    commercialImagery: false,
    groundTruthData: true,
    
    // Exports
    defaultFormat: 'pdf',
    includeRawData: false,
    includeMethodology: true,
    autoGenerateReports: true,
    
    // Security
    twoFactorAuth: true,
    sessionTimeout: 30,
    auditLogging: true,
    dataRetention: 365,
    
    // Appearance
    theme: 'dark',
    compactMode: false,
    animationsEnabled: true,
    highContrastMarkers: false,
  });

  const handleSave = async () => {
    setIsSaving(true);
    // Simulate API call
    await new Promise(resolve => setTimeout(resolve, 1000));
    setIsSaving(false);
    toast.success('Settings saved successfully');
  };

  const updateSetting = (key: string, value: any) => {
    setSettings(prev => ({ ...prev, [key]: value }));
  };

  const renderSection = () => {
    switch (activeSection) {
      case 'profile':
        return (
          <div className="space-y-6">
            <div>
              <h3 className="text-lg font-medium text-foreground mb-4">Profile Information</h3>
              <div className="space-y-4">
                <div className="flex items-center gap-4">
                  <div className="w-20 h-20 rounded-full bg-gradient-to-br from-primary to-primary/60 flex items-center justify-center text-2xl font-bold text-primary-foreground">
                    SC
                  </div>
                  <div>
                    <button className="btn-ghost-neon text-sm">Change Avatar</button>
                  </div>
                </div>
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <label className="text-sm text-muted-foreground block mb-1.5">Display Name</label>
                    <input
                      type="text"
                      value={settings.displayName}
                      onChange={(e) => updateSetting('displayName', e.target.value)}
                      className="w-full px-4 py-2.5 rounded-lg bg-muted/50 border border-border/50 text-foreground focus:outline-none focus:ring-2 focus:ring-primary/50"
                    />
                  </div>
                  <div>
                    <label className="text-sm text-muted-foreground block mb-1.5">Email</label>
                    <input
                      type="email"
                      value={settings.email}
                      onChange={(e) => updateSetting('email', e.target.value)}
                      className="w-full px-4 py-2.5 rounded-lg bg-muted/50 border border-border/50 text-foreground focus:outline-none focus:ring-2 focus:ring-primary/50"
                    />
                  </div>
                  <div>
                    <label className="text-sm text-muted-foreground block mb-1.5">Role</label>
                    <input
                      type="text"
                      value={settings.role}
                      onChange={(e) => updateSetting('role', e.target.value)}
                      className="w-full px-4 py-2.5 rounded-lg bg-muted/50 border border-border/50 text-foreground focus:outline-none focus:ring-2 focus:ring-primary/50"
                    />
                  </div>
                  <div>
                    <label className="text-sm text-muted-foreground block mb-1.5">Organization</label>
                    <input
                      type="text"
                      value={settings.organization}
                      onChange={(e) => updateSetting('organization', e.target.value)}
                      className="w-full px-4 py-2.5 rounded-lg bg-muted/50 border border-border/50 text-foreground focus:outline-none focus:ring-2 focus:ring-primary/50"
                    />
                  </div>
                </div>
              </div>
            </div>
            
            <div className="border-t border-border/30 pt-6">
              <h3 className="text-lg font-medium text-foreground mb-4">Account Actions</h3>
              <div className="flex gap-3">
                <button className="btn-ghost-neon text-sm">Change Password</button>
                <button className="px-4 py-2 rounded-lg text-sm text-danger border border-danger/50 hover:bg-danger/10 transition-colors">
                  Delete Account
                </button>
              </div>
            </div>
          </div>
        );

      case 'notifications':
        return (
          <div className="space-y-6">
            <div>
              <h3 className="text-lg font-medium text-foreground mb-4">Alert Preferences</h3>
              <div className="space-y-4">
                <SettingToggle
                  label="Integrity Gap Alerts"
                  description="Receive immediate alerts when integrity gaps are detected"
                  checked={settings.integrityGapAlerts}
                  onChange={(v) => updateSetting('integrityGapAlerts', v)}
                  icon={<AlertCircle className="w-5 h-5 text-danger" />}
                />
                <SettingToggle
                  label="New Claim Notifications"
                  description="Get notified when new ESG claims require review"
                  checked={settings.newClaimAlerts}
                  onChange={(v) => updateSetting('newClaimAlerts', v)}
                  icon={<FileText className="w-5 h-5 text-primary" />}
                />
                <SettingToggle
                  label="Weekly Digest"
                  description="Receive a weekly summary of portfolio integrity status"
                  checked={settings.weeklyDigest}
                  onChange={(v) => updateSetting('weeklyDigest', v)}
                  icon={<Mail className="w-5 h-5 text-success" />}
                />
              </div>
            </div>

            <div className="border-t border-border/30 pt-6">
              <h3 className="text-lg font-medium text-foreground mb-4">Delivery Channels</h3>
              <div className="space-y-4">
                <SettingToggle
                  label="Email Notifications"
                  description="Send alerts via email"
                  checked={settings.emailAlerts}
                  onChange={(v) => updateSetting('emailAlerts', v)}
                  icon={<Mail className="w-5 h-5 text-muted-foreground" />}
                />
                <SettingToggle
                  label="Push Notifications"
                  description="Enable browser push notifications"
                  checked={settings.pushNotifications}
                  onChange={(v) => updateSetting('pushNotifications', v)}
                  icon={<Smartphone className="w-5 h-5 text-muted-foreground" />}
                />
                <SettingToggle
                  label="Slack Integration"
                  description="Send alerts to connected Slack channels"
                  checked={settings.slackIntegration}
                  onChange={(v) => updateSetting('slackIntegration', v)}
                  icon={<Globe2 className="w-5 h-5 text-muted-foreground" />}
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
                    type="range"
                    min="0"
                    max="100"
                    value={settings.confidenceThreshold}
                    onChange={(e) => updateSetting('confidenceThreshold', parseInt(e.target.value))}
                    className="w-full h-2 rounded-full bg-muted appearance-none cursor-pointer [&::-webkit-slider-thumb]:appearance-none [&::-webkit-slider-thumb]:w-4 [&::-webkit-slider-thumb]:h-4 [&::-webkit-slider-thumb]:rounded-full [&::-webkit-slider-thumb]:bg-primary [&::-webkit-slider-thumb]:cursor-pointer"
                  />
                  <p className="text-xs text-muted-foreground mt-1">Claims above this threshold are marked as verified</p>
                </div>

                <div>
                  <div className="flex items-center justify-between mb-2">
                    <label className="text-sm text-foreground">Auto-Review Threshold</label>
                    <span className="text-sm font-mono text-warning">{settings.autoReviewThreshold}%</span>
                  </div>
                  <input
                    type="range"
                    min="0"
                    max="100"
                    value={settings.autoReviewThreshold}
                    onChange={(e) => updateSetting('autoReviewThreshold', parseInt(e.target.value))}
                    className="w-full h-2 rounded-full bg-muted appearance-none cursor-pointer [&::-webkit-slider-thumb]:appearance-none [&::-webkit-slider-thumb]:w-4 [&::-webkit-slider-thumb]:h-4 [&::-webkit-slider-thumb]:rounded-full [&::-webkit-slider-thumb]:bg-warning [&::-webkit-slider-thumb]:cursor-pointer"
                  />
                  <p className="text-xs text-muted-foreground mt-1">Claims below this threshold are flagged for human review</p>
                </div>
              </div>
            </div>

            <div className="border-t border-border/30 pt-6">
              <h3 className="text-lg font-medium text-foreground mb-4">Analysis Options</h3>
              <div className="space-y-4">
                <SettingToggle
                  label="Multi-Temporal Analysis"
                  description="Compare multiple time periods for change detection"
                  checked={settings.multiTemporalAnalysis}
                  onChange={(v) => updateSetting('multiTemporalAnalysis', v)}
                />
                <SettingToggle
                  label="Include Historical Data"
                  description="Use historical baselines in verification"
                  checked={settings.includeHistoricalData}
                  onChange={(v) => updateSetting('includeHistoricalData', v)}
                />
                <SettingToggle
                  label="SAR Data Analysis"
                  description="Include Synthetic Aperture Radar data for cloud-penetrating analysis"
                  checked={settings.sarDataEnabled}
                  onChange={(v) => updateSetting('sarDataEnabled', v)}
                />
                <SettingToggle
                  label="NDVI Calculation"
                  description="Calculate vegetation indices for land-use claims"
                  checked={settings.ndviCalculation}
                  onChange={(v) => updateSetting('ndviCalculation', v)}
                />
              </div>
            </div>
          </div>
        );

      case 'data-sources':
        return (
          <div className="space-y-6">
            <div>
              <h3 className="text-lg font-medium text-foreground mb-4">Satellite Data Sources</h3>
              <div className="space-y-4">
                <SettingToggle
                  label="Sentinel-2 (Optical)"
                  description="10m resolution optical imagery - primary data source"
                  checked={settings.sentinel2}
                  onChange={(v) => updateSetting('sentinel2', v)}
                  badge="Recommended"
                />
                <SettingToggle
                  label="Sentinel-1 (SAR)"
                  description="Synthetic Aperture Radar - cloud-penetrating capability"
                  checked={settings.sentinel1Sar}
                  onChange={(v) => updateSetting('sentinel1Sar', v)}
                  badge="Recommended"
                />
                <SettingToggle
                  label="Landsat 8"
                  description="30m resolution optical - extended historical archive"
                  checked={settings.landsat8}
                  onChange={(v) => updateSetting('landsat8', v)}
                />
                <SettingToggle
                  label="Commercial High-Resolution"
                  description="Sub-meter resolution for detailed verification (additional cost)"
                  checked={settings.commercialImagery}
                  onChange={(v) => updateSetting('commercialImagery', v)}
                  badge="Premium"
                  badgeVariant="warning"
                />
              </div>
            </div>

            <div className="border-t border-border/30 pt-6">
              <h3 className="text-lg font-medium text-foreground mb-4">Supplementary Data</h3>
              <div className="space-y-4">
                <SettingToggle
                  label="Ground Truth Integration"
                  description="Include verified ground-truth data when available"
                  checked={settings.groundTruthData}
                  onChange={(v) => updateSetting('groundTruthData', v)}
                />
              </div>
            </div>
          </div>
        );

      case 'exports':
        return (
          <div className="space-y-6">
            <div>
              <h3 className="text-lg font-medium text-foreground mb-4">Report Settings</h3>
              <div className="space-y-4">
                <div>
                  <label className="text-sm text-muted-foreground block mb-2">Default Export Format</label>
                  <div className="flex gap-2">
                    {['pdf', 'docx', 'json', 'csv'].map(format => (
                      <button
                        key={format}
                        onClick={() => updateSetting('defaultFormat', format)}
                        className={cn(
                          "px-4 py-2 rounded-lg text-sm uppercase font-mono transition-all",
                          settings.defaultFormat === format
                            ? "bg-primary text-primary-foreground"
                            : "bg-muted/50 text-muted-foreground hover:text-foreground border border-border/50"
                        )}
                      >
                        {format}
                      </button>
                    ))}
                  </div>
                </div>

                <SettingToggle
                  label="Include Methodology"
                  description="Append detailed methodology section to reports"
                  checked={settings.includeMethodology}
                  onChange={(v) => updateSetting('includeMethodology', v)}
                />
                <SettingToggle
                  label="Include Raw Data"
                  description="Attach raw satellite data and analysis outputs"
                  checked={settings.includeRawData}
                  onChange={(v) => updateSetting('includeRawData', v)}
                />
                <SettingToggle
                  label="Auto-Generate Reports"
                  description="Automatically generate reports when analysis completes"
                  checked={settings.autoGenerateReports}
                  onChange={(v) => updateSetting('autoGenerateReports', v)}
                />
              </div>
            </div>
          </div>
        );

      case 'security':
        return (
          <div className="space-y-6">
            <div>
              <h3 className="text-lg font-medium text-foreground mb-4">Authentication</h3>
              <div className="space-y-4">
                <SettingToggle
                  label="Two-Factor Authentication"
                  description="Require 2FA for all login attempts"
                  checked={settings.twoFactorAuth}
                  onChange={(v) => updateSetting('twoFactorAuth', v)}
                  icon={<Shield className="w-5 h-5 text-success" />}
                />
                <div>
                  <label className="text-sm text-muted-foreground block mb-2">Session Timeout (minutes)</label>
                  <select
                    value={settings.sessionTimeout}
                    onChange={(e) => updateSetting('sessionTimeout', parseInt(e.target.value))}
                    className="w-48 px-4 py-2.5 rounded-lg bg-muted/50 border border-border/50 text-foreground focus:outline-none focus:ring-2 focus:ring-primary/50"
                  >
                    <option value={15}>15 minutes</option>
                    <option value={30}>30 minutes</option>
                    <option value={60}>1 hour</option>
                    <option value={120}>2 hours</option>
                  </select>
                </div>
              </div>
            </div>

            <div className="border-t border-border/30 pt-6">
              <h3 className="text-lg font-medium text-foreground mb-4">Data & Privacy</h3>
              <div className="space-y-4">
                <SettingToggle
                  label="Audit Logging"
                  description="Log all user actions for compliance purposes"
                  checked={settings.auditLogging}
                  onChange={(v) => updateSetting('auditLogging', v)}
                />
                <div>
                  <label className="text-sm text-muted-foreground block mb-2">Data Retention Period</label>
                  <select
                    value={settings.dataRetention}
                    onChange={(e) => updateSetting('dataRetention', parseInt(e.target.value))}
                    className="w-48 px-4 py-2.5 rounded-lg bg-muted/50 border border-border/50 text-foreground focus:outline-none focus:ring-2 focus:ring-primary/50"
                  >
                    <option value={90}>90 days</option>
                    <option value={180}>180 days</option>
                    <option value={365}>1 year</option>
                    <option value={730}>2 years</option>
                    <option value={1825}>5 years</option>
                  </select>
                </div>
              </div>
            </div>
          </div>
        );

      case 'appearance':
        return (
          <div className="space-y-6">
            <div>
              <h3 className="text-lg font-medium text-foreground mb-4">Theme</h3>
              <div className="flex gap-3">
                {[
                  { id: 'dark', label: 'Dark', desc: 'Default dark theme' },
                  { id: 'light', label: 'Light', desc: 'Light mode (coming soon)', disabled: true },
                  { id: 'system', label: 'System', desc: 'Match system preference', disabled: true },
                ].map(theme => (
                  <button
                    key={theme.id}
                    onClick={() => !theme.disabled && updateSetting('theme', theme.id)}
                    disabled={theme.disabled}
                    className={cn(
                      "flex-1 p-4 rounded-lg border transition-all text-left",
                      settings.theme === theme.id
                        ? "border-primary bg-primary/10"
                        : "border-border/50 hover:border-primary/30",
                      theme.disabled && "opacity-50 cursor-not-allowed"
                    )}
                  >
                    <span className="text-sm font-medium text-foreground block">{theme.label}</span>
                    <span className="text-xs text-muted-foreground">{theme.desc}</span>
                  </button>
                ))}
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
                <SettingToggle
                  label="High Contrast Markers"
                  description="Use larger, higher-contrast claim markers on the globe"
                  checked={settings.highContrastMarkers}
                  onChange={(v) => updateSetting('highContrastMarkers', v)}
                />
              </div>
            </div>
          </div>
        );

      case 'api':
        return (
          <div className="space-y-6">
            <div>
              <h3 className="text-lg font-medium text-foreground mb-4">API Access</h3>
              <div className="glass-panel p-4 mb-4">
                <div className="flex items-center justify-between mb-2">
                  <span className="text-sm text-muted-foreground">API Key</span>
                  <button className="text-xs text-primary hover:text-primary/80">Regenerate</button>
                </div>
                <div className="flex items-center gap-2">
                  <code className="flex-1 px-3 py-2 rounded bg-muted font-mono text-sm text-foreground">
                    pk_live_••••••••••••••••••••••••
                  </code>
                  <button className="px-3 py-2 rounded-lg bg-muted/50 text-sm text-muted-foreground hover:text-foreground transition-colors">
                    Copy
                  </button>
                </div>
              </div>
              <p className="text-xs text-muted-foreground">
                Use this API key to access PHAROS-INTEGRITY programmatically. Keep it secure and never expose it in client-side code.
              </p>
            </div>

            <div className="border-t border-border/30 pt-6">
              <h3 className="text-lg font-medium text-foreground mb-4">Integrations</h3>
              <div className="space-y-3">
                {[
                  { name: 'Bloomberg Terminal', status: 'connected', icon: '📊' },
                  { name: 'Salesforce', status: 'available', icon: '☁️' },
                  { name: 'Microsoft Power BI', status: 'available', icon: '📈' },
                  { name: 'Slack', status: 'connected', icon: '💬' },
                ].map(integration => (
                  <div key={integration.name} className="flex items-center justify-between p-3 rounded-lg bg-muted/30 border border-border/30">
                    <div className="flex items-center gap-3">
                      <span className="text-xl">{integration.icon}</span>
                      <span className="text-sm font-medium text-foreground">{integration.name}</span>
                    </div>
                    {integration.status === 'connected' ? (
                      <span className="text-xs text-success flex items-center gap-1">
                        <Check className="w-3 h-3" /> Connected
                      </span>
                    ) : (
                      <button className="text-xs text-primary hover:text-primary/80">Connect</button>
                    )}
                  </div>
                ))}
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
      {/* Header */}
      <motion.header 
        className="h-16 border-b border-border/30 glass-panel flex items-center justify-between px-6"
        initial={{ opacity: 0, y: -20 }}
        animate={{ opacity: 1, y: 0 }}
      >
        <div>
          <h1 className="text-lg font-semibold text-foreground">Settings</h1>
          <p className="text-xs text-muted-foreground">Configure your PHAROS-INTEGRITY experience</p>
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

      {/* Content */}
      <div className="flex-1 flex overflow-hidden">
        {/* Sidebar */}
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
                  "w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-left transition-all",
                  activeSection === section.id
                    ? "bg-primary/15 text-primary"
                    : "text-muted-foreground hover:text-foreground hover:bg-muted/30"
                )}
                initial={{ opacity: 0, x: -10 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ delay: i * 0.05 }}
              >
                <section.icon className="w-4 h-4" />
                <span className="text-sm">{section.label}</span>
                {activeSection === section.id && (
                  <ChevronRight className="w-4 h-4 ml-auto" />
                )}
              </motion.button>
            ))}
          </div>
        </motion.nav>

        {/* Main Content */}
        <motion.div 
          className="flex-1 p-6 overflow-y-auto"
          key={activeSection}
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.2 }}
        >
          <div className="max-w-2xl">
            {renderSection()}
          </div>
        </motion.div>
      </div>
    </AppLayout>
  );
};

// Toggle Component
const SettingToggle = ({ 
  label, 
  description, 
  checked, 
  onChange, 
  icon,
  badge,
  badgeVariant = 'success'
}: {
  label: string;
  description: string;
  checked: boolean;
  onChange: (v: boolean) => void;
  icon?: React.ReactNode;
  badge?: string;
  badgeVariant?: 'success' | 'warning';
}) => (
  <div className="flex items-start justify-between gap-4 p-3 rounded-lg hover:bg-muted/20 transition-colors">
    <div className="flex items-start gap-3">
      {icon && <div className="mt-0.5">{icon}</div>}
      <div>
        <div className="flex items-center gap-2">
          <span className="text-sm font-medium text-foreground">{label}</span>
          {badge && (
            <span className={cn(
              "text-[10px] px-1.5 py-0.5 rounded uppercase font-medium",
              badgeVariant === 'success' ? "bg-success/20 text-success" : "bg-warning/20 text-warning"
            )}>
              {badge}
            </span>
          )}
        </div>
        <span className="text-xs text-muted-foreground">{description}</span>
      </div>
    </div>
    <Switch checked={checked} onCheckedChange={onChange} />
  </div>
);

export default Settings;
