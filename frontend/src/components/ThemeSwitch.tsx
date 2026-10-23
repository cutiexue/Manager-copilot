import { useTheme, type ThemeChoice } from '../theme';
import Icon, { type IconName } from './Icon';

const OPTIONS: { value: ThemeChoice; label: string; icon: IconName }[] = [
  { value: 'light', label: 'Light', icon: 'sun' },
  { value: 'dark', label: 'Dark', icon: 'moon' },
  { value: 'system', label: 'Match system', icon: 'monitor' },
];

// Three-way theme switch for the sidebar footer: icons, with the name on hover and for screen readers.
export default function ThemeSwitch() {
  const [choice, setChoice] = useTheme();

  return (
    <div className="theme-switch" role="group" aria-label="Theme">
      {OPTIONS.map((option) => (
        <button
          key={option.value}
          type="button"
          className="theme-opt"
          title={option.label}
          aria-label={option.label}
          aria-pressed={choice === option.value}
          onClick={() => setChoice(option.value)}
        >
          <Icon name={option.icon} size={14} />
        </button>
      ))}
    </div>
  );
}
