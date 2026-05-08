import fs, { promises } from 'fs';

async function isType(fsStatType, statsMethodName, filePath) {
	if (typeof filePath !== 'string') {
		throw new TypeError(`Expected a string, got ${typeof filePath}`);
	}

	try {
		const stats = await promises[fsStatType](filePath);
		return stats[statsMethodName]();
	} catch (error) {
		if (error.code === 'ENOENT') {
			return false;
		}

		throw error;
	}
}

function isTypeSync(fsStatType, statsMethodName, filePath) {
	if (typeof filePath !== 'string') {
		throw new TypeError(`Expected a string, got ${typeof filePath}`);
	}

	try {
		return fs[fsStatType](filePath)[statsMethodName]();
	} catch (error) {
		if (error.code === 'ENOENT') {
			return false;
		}

		throw error;
	}
}

const isFile = isType.bind(null, 'stat', 'isFile');
const isDirectory = isType.bind(null, 'stat', 'isDirectory');
const isSymlink = isType.bind(null, 'lstat', 'isSymbolicLink');
const isFileSync = isTypeSync.bind(null, 'statSync', 'isFile');
const isDirectorySync = isTypeSync.bind(null, 'statSync', 'isDirectory');
const isSymlinkSync = isTypeSync.bind(null, 'lstatSync', 'isSymbolicLink');

export { isDirectory, isDirectorySync, isFile, isFileSync, isSymlink, isSymlinkSync };
