import { App, Modal, Notice, Plugin, PluginSettingTab, Setting, TFile, TAbstractFile, EventRef } from 'obsidian';

interface ZoteroSyncSettings {
	zoteroUserId: string;
	zoteroApiKey: string;
	n8nWebhookUrl: string;
	literatureNotesPath: string;
	showDetailedResults: boolean;
	// Auto-sync settings
	autoSyncEnabled: boolean;
	syncOnVaultChange: boolean;
	zoteroCheckInterval: number; // minutes
	debounceDelay: number; // milliseconds
	silentAutoSync: boolean;
	onlyWebhookOnChanges: boolean;
}

const DEFAULT_SETTINGS: ZoteroSyncSettings = {
	zoteroUserId: '',
	zoteroApiKey: '',
	n8nWebhookUrl: '',
	literatureNotesPath: '80. References/81. zotero',
	showDetailedResults: true,
	autoSyncEnabled: false,
	syncOnVaultChange: true,
	zoteroCheckInterval: 30, // 30 minutes
	debounceDelay: 5000, // 5 seconds
	silentAutoSync: true,
	onlyWebhookOnChanges: true
}

interface ZoteroArticle {
	key: string;
	title: string;
	collection: string;
}

interface ObsidianArticle {
	key: string;
	title: string;
	collection: string;
	filePath: string;
}

interface SyncComparison {
	added: ZoteroArticle[];
	deleted: ObsidianArticle[];
	moved: {
		key: string;
		title: string;
		oldCollection: string;
		newCollection: string;
		filePath: string;
	}[];
	statistics: {
		zoteroTotal: number;
		obsidianTotal: number;
		synced: number;
		addedCount: number;
		deletedCount: number;
		movedCount: number;
	};
	timestamp: string;
}

export default class ZoteroSyncPlugin extends Plugin {
	settings: ZoteroSyncSettings;
	private debounceTimer: NodeJS.Timeout | null = null;
	private zoteroCheckInterval: NodeJS.Timeout | null = null;
	private vaultListeners: EventRef[] = [];
	private lastComparison: SyncComparison | null = null;
	private isChecking = false;

	async onload() {
		await this.loadSettings();

		// Ribbon icon
		this.addRibbonIcon('sync', 'Check Zotero Sync', async () => {
			await this.checkSyncStatus(false); // Manual check - not silent
		});

		// Commands
		this.addCommand({
			id: 'check-zotero-sync',
			name: 'Check Zotero sync status',
			callback: async () => {
				await this.checkSyncStatus(false);
			}
		});

		this.addCommand({
			id: 'toggle-auto-sync',
			name: 'Toggle auto-sync',
			callback: async () => {
				this.settings.autoSyncEnabled = !this.settings.autoSyncEnabled;
				await this.saveSettings();
				new Notice(`Auto-sync ${this.settings.autoSyncEnabled ? 'enabled' : 'disabled'}`);

				if (this.settings.autoSyncEnabled) {
					this.startAutoSync();
				} else {
					this.stopAutoSync();
				}
			}
		});

		// Settings tab
		this.addSettingTab(new ZoteroSyncSettingTab(this.app, this));

		// Start auto-sync if enabled
		if (this.settings.autoSyncEnabled) {
			this.startAutoSync();
		}
	}

	onunload() {
		this.stopAutoSync();
	}

	startAutoSync() {
		console.log('Starting Zotero auto-sync...');

		// Setup vault change listeners
		if (this.settings.syncOnVaultChange) {
			this.setupVaultListeners();
		}

		// Setup periodic Zotero check
		if (this.settings.zoteroCheckInterval > 0) {
			const intervalMs = this.settings.zoteroCheckInterval * 60 * 1000;
			this.zoteroCheckInterval = setInterval(() => {
				this.scheduleCheck(true);
			}, intervalMs);
			console.log(`Zotero check interval set to ${this.settings.zoteroCheckInterval} minutes`);
		}

		// Do initial check
		this.scheduleCheck(true);
	}

	stopAutoSync() {
		console.log('Stopping Zotero auto-sync...');

		// Clear debounce timer
		if (this.debounceTimer) {
			clearTimeout(this.debounceTimer);
			this.debounceTimer = null;
		}

		// Clear interval
		if (this.zoteroCheckInterval) {
			clearInterval(this.zoteroCheckInterval);
			this.zoteroCheckInterval = null;
		}

		// Remove vault listeners
		this.vaultListeners.forEach(ref => this.app.vault.offref(ref));
		this.vaultListeners = [];
	}

	setupVaultListeners() {
		const vault = this.app.vault;
		const notesPath = this.settings.literatureNotesPath;

		// File created
		const onCreate = vault.on('create', (file: TAbstractFile) => {
			if (file instanceof TFile && this.isLiteratureNote(file)) {
				console.log('Literature note created:', file.path);
				this.scheduleCheck(true);
			}
		});

		// File deleted
		const onDelete = vault.on('delete', (file: TAbstractFile) => {
			if (file instanceof TFile && this.isLiteratureNote(file)) {
				console.log('Literature note deleted:', file.path);
				this.scheduleCheck(true);
			}
		});

		// File renamed/moved
		const onRename = vault.on('rename', (file: TAbstractFile, oldPath: string) => {
			if (file instanceof TFile && (this.isLiteratureNote(file) || oldPath.startsWith(notesPath))) {
				console.log('Literature note renamed/moved:', oldPath, '->', file.path);
				this.scheduleCheck(true);
			}
		});

		this.vaultListeners.push(onCreate, onDelete, onRename);
	}

	isLiteratureNote(file: TFile): boolean {
		return file.path.startsWith(this.settings.literatureNotesPath) &&
		       file.extension === 'md' &&
		       !file.path.includes('/img/');
	}

	scheduleCheck(silent: boolean) {
		// Clear existing timer
		if (this.debounceTimer) {
			clearTimeout(this.debounceTimer);
		}

		// Schedule new check with debounce
		this.debounceTimer = setTimeout(() => {
			this.checkSyncStatus(silent);
		}, this.settings.debounceDelay);
	}

	async checkSyncStatus(silent: boolean = false) {
		// Prevent concurrent checks
		if (this.isChecking) {
			console.log('Sync check already in progress, skipping...');
			return;
		}

		if (!this.settings.zoteroUserId || !this.settings.zoteroApiKey) {
			if (!silent) {
				new Notice('Please configure Zotero credentials in settings');
			}
			return;
		}

		this.isChecking = true;

		try {
			if (!silent) {
				new Notice('Fetching Zotero data...');
			}

			// Fetch Zotero articles
			const zoteroArticles = await this.fetchZoteroArticles();
			if (!silent) {
				new Notice(`Found ${zoteroArticles.length} Zotero articles`);
			}

			// Scan Obsidian vault
			const obsidianArticles = await this.scanObsidianVault();
			if (!silent) {
				new Notice(`Found ${obsidianArticles.length} Obsidian files`);
			}

			// Compare
			const comparison = this.compareSync(zoteroArticles, obsidianArticles);
			comparison.timestamp = new Date().toISOString();

			// Check if there are changes
			const hasChanges = comparison.statistics.addedCount > 0 ||
			                   comparison.statistics.deletedCount > 0 ||
			                   comparison.statistics.movedCount > 0;

			// Send to n8n webhook
			if (this.settings.n8nWebhookUrl) {
				// Only send if there are changes (when onlyWebhookOnChanges is true)
				if (!this.settings.onlyWebhookOnChanges || hasChanges) {
					await this.sendToWebhook(comparison);
					if (!silent) {
						new Notice('Sync status sent to n8n webhook');
					} else {
						console.log('Sync status sent to n8n webhook:', {
							added: comparison.statistics.addedCount,
							deleted: comparison.statistics.deletedCount,
							moved: comparison.statistics.movedCount
						});
					}
				} else {
					console.log('No changes detected, skipping webhook');
				}
			}

			// Save last comparison
			this.lastComparison = comparison;

			// Show results
			if (!silent && this.settings.showDetailedResults) {
				new SyncResultModal(this.app, comparison).open();
			} else if (!silent) {
				new Notice(
					`Sync check complete:\n` +
					`Added: ${comparison.statistics.addedCount}\n` +
					`Deleted: ${comparison.statistics.deletedCount}\n` +
					`Moved: ${comparison.statistics.movedCount}`
				);
			} else if (hasChanges) {
				// Show minimal notice for auto-sync changes
				new Notice(
					`📚 Zotero sync: ${comparison.statistics.addedCount} added, ` +
					`${comparison.statistics.deletedCount} deleted, ` +
					`${comparison.statistics.movedCount} moved`,
					5000
				);
			}

		} catch (error) {
			console.error('Sync check failed:', error);
			if (!silent) {
				new Notice(`Error: ${error.message}`);
			}
		} finally {
			this.isChecking = false;
		}
	}

	async fetchZoteroArticles(): Promise<ZoteroArticle[]> {
		const articles: ZoteroArticle[] = [];

		// Build collection hierarchy first
		const collections = await this.fetchZoteroCollections();
		const collectionPaths = this.buildCollectionHierarchy(collections);

		// Fetch all journal articles with pagination
		let start = 0;
		const limit = 100;

		while (true) {
			const url = `https://api.zotero.org/users/${this.settings.zoteroUserId}/items?` +
				`itemType=journalArticle&start=${start}&limit=${limit}`;

			const response = await fetch(url, {
				headers: {
					'Zotero-API-Key': this.settings.zoteroApiKey
				}
			});

			if (!response.ok) {
				throw new Error(`Zotero API error: ${response.statusText}`);
			}

			const items = await response.json();

			if (items.length === 0) break;

			for (const item of items) {
				const data = item.data;
				const itemCollections = data.collections || [];

				// Get first collection path or 'Uncategorized'
				let collectionPath = 'Uncategorized';
				if (itemCollections.length > 0) {
					const firstCollKey = itemCollections[0];
					collectionPath = collectionPaths[firstCollKey] || 'Uncategorized';
				}

				articles.push({
					key: data.key,
					title: data.title || 'Untitled',
					collection: collectionPath
				});
			}

			if (items.length < limit) break;
			start += limit;
		}

		return articles;
	}

	async fetchZoteroCollections(): Promise<any[]> {
		const url = `https://api.zotero.org/users/${this.settings.zoteroUserId}/collections`;

		const response = await fetch(url, {
			headers: {
				'Zotero-API-Key': this.settings.zoteroApiKey
			}
		});

		if (!response.ok) {
			throw new Error(`Zotero API error: ${response.statusText}`);
		}

		return await response.json();
	}

	buildCollectionHierarchy(collections: any[]): Record<string, string> {
		const collectionDict: Record<string, any> = {};
		const collectionPaths: Record<string, string> = {};

		// Build dictionary
		for (const coll of collections) {
			collectionDict[coll.key] = coll;
		}

		// Recursive function to build path
		const getPath = (key: string): string => {
			if (collectionPaths[key]) {
				return collectionPaths[key];
			}

			const coll = collectionDict[key];
			if (!coll) return '';

			const parentKey = coll.data.parentCollection;
			if (parentKey && parentKey !== 'false') {
				const parentPath = getPath(parentKey);
				const path = parentPath ? `${parentPath}/${coll.data.name}` : coll.data.name;
				collectionPaths[key] = path;
				return path;
			} else {
				collectionPaths[key] = coll.data.name;
				return coll.data.name;
			}
		};

		// Build all paths
		for (const key in collectionDict) {
			getPath(key);
		}

		return collectionPaths;
	}

	async scanObsidianVault(): Promise<ObsidianArticle[]> {
		const articles: ObsidianArticle[] = [];
		const notesPath = this.settings.literatureNotesPath;

		// Get all markdown files in the literature notes folder
		const files = this.app.vault.getMarkdownFiles();

		for (const file of files) {
			// Check if file is in literature notes path
			if (!file.path.startsWith(notesPath)) continue;

			// Skip img folder
			if (file.path.includes('/img/')) continue;

			// Extract key from filename: {title}_{KEY}.md
			const filename = file.basename;
			const parts = filename.split('_');

			if (parts.length >= 2) {
				const key = parts[parts.length - 1]; // Last part is key
				const titlePart = parts.slice(0, -1).join('_'); // Rest is title

				// Get collection from folder structure
				const relativePath = file.path.substring(notesPath.length + 1);
				const folderParts = relativePath.split('/');
				const collection = folderParts.length > 1
					? folderParts.slice(0, -1).join('/')
					: 'Uncategorized';

				articles.push({
					key: key,
					title: titlePart,
					collection: collection,
					filePath: file.path
				});
			}
		}

		return articles;
	}

	sanitizeFolderName(name: string): string {
		return name
			.replace(/[\/\\:]/g, '-')
			.replace(/[*?"<>|]/g, '')
			.trim();
	}

	normalizeCollectionPath(path: string): string {
		const parts = path.split('/');
		const sanitized = parts.map(p => this.sanitizeFolderName(p));
		return sanitized.join('/');
	}

	compareSync(zoteroArticles: ZoteroArticle[], obsidianArticles: ObsidianArticle[]): SyncComparison {
		const zoteroMap = new Map(zoteroArticles.map(a => [a.key, a]));
		const obsidianMap = new Map(obsidianArticles.map(a => [a.key, a]));

		// Added: in Zotero but not in Obsidian
		const added: ZoteroArticle[] = [];
		for (const [key, article] of zoteroMap) {
			if (!obsidianMap.has(key)) {
				added.push(article);
			}
		}

		// Deleted: in Obsidian but not in Zotero
		const deleted: ObsidianArticle[] = [];
		for (const [key, article] of obsidianMap) {
			if (!zoteroMap.has(key)) {
				deleted.push(article);
			}
		}

		// Moved: same key but different collection
		const moved: any[] = [];
		for (const [key, zotArticle] of zoteroMap) {
			const obsArticle = obsidianMap.get(key);
			if (obsArticle) {
				const zotCollNormalized = this.normalizeCollectionPath(zotArticle.collection);
				const obsCollNormalized = obsArticle.collection;

				if (zotCollNormalized !== obsCollNormalized) {
					moved.push({
						key: key,
						title: zotArticle.title,
						oldCollection: obsArticle.collection,
						newCollection: zotArticle.collection,
						filePath: obsArticle.filePath
					});
				}
			}
		}

		return {
			added: added.sort((a, b) => a.collection.localeCompare(b.collection)),
			deleted: deleted.sort((a, b) => a.collection.localeCompare(b.collection)),
			moved: moved.sort((a, b) => a.newCollection.localeCompare(b.newCollection)),
			statistics: {
				zoteroTotal: zoteroArticles.length,
				obsidianTotal: obsidianArticles.length,
				synced: zoteroArticles.length - added.length,
				addedCount: added.length,
				deletedCount: deleted.length,
				movedCount: moved.length
			},
			timestamp: new Date().toISOString()
		};
	}

	async sendToWebhook(comparison: SyncComparison) {
		if (!this.settings.n8nWebhookUrl) return;

		const response = await fetch(this.settings.n8nWebhookUrl, {
			method: 'POST',
			headers: {
				'Content-Type': 'application/json'
			},
			body: JSON.stringify(comparison)
		});

		if (!response.ok) {
			throw new Error(`Webhook error: ${response.statusText}`);
		}
	}

	async loadSettings() {
		this.settings = Object.assign({}, DEFAULT_SETTINGS, await this.loadData());
	}

	async saveSettings() {
		await this.saveData(this.settings);
	}
}

class SyncResultModal extends Modal {
	comparison: SyncComparison;

	constructor(app: App, comparison: SyncComparison) {
		super(app);
		this.comparison = comparison;
	}

	onOpen() {
		const { contentEl } = this;
		const c = this.comparison;

		contentEl.empty();
		contentEl.createEl('h2', { text: 'Zotero ↔ Obsidian Sync Status' });

		// Timestamp
		const timestamp = new Date(c.timestamp).toLocaleString();
		contentEl.createEl('p', {
			text: `Last checked: ${timestamp}`,
			cls: 'sync-timestamp'
		});

		// Statistics
		const stats = contentEl.createDiv({ cls: 'sync-stats' });
		stats.createEl('h3', { text: '📊 Statistics' });
		const statsList = stats.createEl('ul');
		statsList.createEl('li', { text: `Zotero items: ${c.statistics.zoteroTotal}` });
		statsList.createEl('li', { text: `Obsidian files: ${c.statistics.obsidianTotal}` });
		statsList.createEl('li', { text: `Synced: ${c.statistics.synced}` });

		// Differences
		const diff = contentEl.createDiv({ cls: 'sync-diff' });
		diff.createEl('h3', { text: '🔍 Differences' });
		const diffList = diff.createEl('ul');
		diffList.createEl('li', { text: `Added (Zotero only): ${c.statistics.addedCount}` });
		diffList.createEl('li', { text: `Deleted (Obsidian only): ${c.statistics.deletedCount}` });
		diffList.createEl('li', { text: `Moved (collection changed): ${c.statistics.movedCount}` });

		// Added items
		if (c.added.length > 0) {
			const added = contentEl.createDiv({ cls: 'sync-added' });
			added.createEl('h3', { text: `📝 Added Items (${c.added.length})` });
			const addedList = added.createEl('ul');

			// Group by collection
			const byCollection = new Map<string, ZoteroArticle[]>();
			for (const item of c.added) {
				if (!byCollection.has(item.collection)) {
					byCollection.set(item.collection, []);
				}
				byCollection.get(item.collection)!.push(item);
			}

			for (const [collection, items] of byCollection) {
				const collItem = addedList.createEl('li');
				collItem.createEl('strong', { text: `[${collection}] (${items.length})` });
				const itemList = collItem.createEl('ul');
				for (const item of items.slice(0, 10)) {
					itemList.createEl('li', { text: `${item.title.substring(0, 60)} (${item.key})` });
				}
				if (items.length > 10) {
					itemList.createEl('li', { text: `... and ${items.length - 10} more` });
				}
			}
		}

		// Moved items
		if (c.moved.length > 0) {
			const moved = contentEl.createDiv({ cls: 'sync-moved' });
			moved.createEl('h3', { text: `📦 Moved Items (${c.moved.length})` });
			const movedList = moved.createEl('ul');

			for (const item of c.moved.slice(0, 20)) {
				const li = movedList.createEl('li');
				li.createEl('div', { text: `${item.title.substring(0, 60)}` });
				li.createEl('div', {
					text: `${item.oldCollection} → ${item.newCollection}`,
					cls: 'sync-move-arrow'
				});
			}
			if (c.moved.length > 20) {
				movedList.createEl('li', { text: `... and ${c.moved.length - 20} more` });
			}
		}

		// Close button
		const closeBtn = contentEl.createEl('button', { text: 'Close' });
		closeBtn.addEventListener('click', () => this.close());
	}

	onClose() {
		const { contentEl } = this;
		contentEl.empty();
	}
}

class ZoteroSyncSettingTab extends PluginSettingTab {
	plugin: ZoteroSyncPlugin;

	constructor(app: App, plugin: ZoteroSyncPlugin) {
		super(app, plugin);
		this.plugin = plugin;
	}

	display(): void {
		const { containerEl } = this;
		containerEl.empty();

		containerEl.createEl('h2', { text: 'Zotero Sync Checker Settings' });

		// Zotero API Settings
		containerEl.createEl('h3', { text: 'Zotero API Credentials' });

		new Setting(containerEl)
			.setName('Zotero User ID')
			.setDesc('Your Zotero user ID (find at zotero.org/settings/keys)')
			.addText(text => text
				.setPlaceholder('123456')
				.setValue(this.plugin.settings.zoteroUserId)
				.onChange(async (value) => {
					this.plugin.settings.zoteroUserId = value;
					await this.plugin.saveSettings();
				}));

		new Setting(containerEl)
			.setName('Zotero API Key')
			.setDesc('Your Zotero API key (create at zotero.org/settings/keys)')
			.addText(text => text
				.setPlaceholder('xxxxxxxxxxxxxxxxxxxx')
				.setValue(this.plugin.settings.zoteroApiKey)
				.onChange(async (value) => {
					this.plugin.settings.zoteroApiKey = value;
					await this.plugin.saveSettings();
				}));

		// Webhook Settings
		containerEl.createEl('h3', { text: 'Webhook Settings' });

		new Setting(containerEl)
			.setName('n8n Webhook URL')
			.setDesc('n8n webhook URL to send sync status (leave empty to disable)')
			.addText(text => text
				.setPlaceholder('https://your-n8n.com/webhook/zotero-sync')
				.setValue(this.plugin.settings.n8nWebhookUrl)
				.onChange(async (value) => {
					this.plugin.settings.n8nWebhookUrl = value;
					await this.plugin.saveSettings();
				}));

		new Setting(containerEl)
			.setName('Only send webhook on changes')
			.setDesc('Only send webhook when there are actual changes (added/deleted/moved items)')
			.addToggle(toggle => toggle
				.setValue(this.plugin.settings.onlyWebhookOnChanges)
				.onChange(async (value) => {
					this.plugin.settings.onlyWebhookOnChanges = value;
					await this.plugin.saveSettings();
				}));

		// Vault Settings
		containerEl.createEl('h3', { text: 'Vault Settings' });

		new Setting(containerEl)
			.setName('Literature Notes Path')
			.setDesc('Path to your literature notes folder in vault')
			.addText(text => text
				.setPlaceholder('80. References/81. zotero')
				.setValue(this.plugin.settings.literatureNotesPath)
				.onChange(async (value) => {
					this.plugin.settings.literatureNotesPath = value;
					await this.plugin.saveSettings();
				}));

		new Setting(containerEl)
			.setName('Show Detailed Results')
			.setDesc('Show detailed results modal after manual sync check')
			.addToggle(toggle => toggle
				.setValue(this.plugin.settings.showDetailedResults)
				.onChange(async (value) => {
					this.plugin.settings.showDetailedResults = value;
					await this.plugin.saveSettings();
				}));

		// Auto-Sync Settings
		containerEl.createEl('h3', { text: 'Auto-Sync Settings' });

		new Setting(containerEl)
			.setName('Enable Auto-Sync')
			.setDesc('Automatically check for sync changes')
			.addToggle(toggle => toggle
				.setValue(this.plugin.settings.autoSyncEnabled)
				.onChange(async (value) => {
					this.plugin.settings.autoSyncEnabled = value;
					await this.plugin.saveSettings();

					if (value) {
						this.plugin.startAutoSync();
						new Notice('Auto-sync enabled');
					} else {
						this.plugin.stopAutoSync();
						new Notice('Auto-sync disabled');
					}
				}));

		new Setting(containerEl)
			.setName('Sync on Vault Changes')
			.setDesc('Trigger sync check when literature notes are created, deleted, or moved')
			.addToggle(toggle => toggle
				.setValue(this.plugin.settings.syncOnVaultChange)
				.onChange(async (value) => {
					this.plugin.settings.syncOnVaultChange = value;
					await this.plugin.saveSettings();

					// Restart auto-sync to apply changes
					if (this.plugin.settings.autoSyncEnabled) {
						this.plugin.stopAutoSync();
						this.plugin.startAutoSync();
					}
				}));

		new Setting(containerEl)
			.setName('Zotero Check Interval')
			.setDesc('How often to check Zotero for changes (in minutes, 0 to disable)')
			.addText(text => text
				.setPlaceholder('30')
				.setValue(String(this.plugin.settings.zoteroCheckInterval))
				.onChange(async (value) => {
					const num = parseInt(value);
					if (!isNaN(num) && num >= 0) {
						this.plugin.settings.zoteroCheckInterval = num;
						await this.plugin.saveSettings();

						// Restart auto-sync to apply new interval
						if (this.plugin.settings.autoSyncEnabled) {
							this.plugin.stopAutoSync();
							this.plugin.startAutoSync();
						}
					}
				}));

		new Setting(containerEl)
			.setName('Debounce Delay')
			.setDesc('Wait time after vault changes before checking (in milliseconds)')
			.addText(text => text
				.setPlaceholder('5000')
				.setValue(String(this.plugin.settings.debounceDelay))
				.onChange(async (value) => {
					const num = parseInt(value);
					if (!isNaN(num) && num >= 0) {
						this.plugin.settings.debounceDelay = num;
						await this.plugin.saveSettings();
					}
				}));

		new Setting(containerEl)
			.setName('Silent Auto-Sync')
			.setDesc('Hide notifications during automatic sync checks (only show when changes are found)')
			.addToggle(toggle => toggle
				.setValue(this.plugin.settings.silentAutoSync)
				.onChange(async (value) => {
					this.plugin.settings.silentAutoSync = value;
					await this.plugin.saveSettings();
				}));
	}
}
